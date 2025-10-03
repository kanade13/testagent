#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
excel_to_json.py

A robust, configurable Excel→JSON converter for "operation steps" tables.
- Groups rows by case/task ID
- Orders by step index (numeric or lexicographic)
- Normalizes/ffill IDs from merged-like layouts
- Parses params as JSON or "k=v; k2=v2" strings
- Emits one combined JSON (default) or per-case JSON files

Usage
-----
python excel_to_json.py --input my.xlsx --sheet "Sheet1" --output out.json \
    --case-id "case" --step-col "step" --action-col "action" \
    --tool-col "tool" --params-col "params" --notes-col "notes"

Or drive it with a YAML config:
python excel_to_json.py --config config.yaml

Dependencies: pandas, openpyxl (for .xlsx). Install if missing:
pip install pandas openpyxl pyyaml
"""
from __future__ import annotations
import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple, Union

# Optional deps handling
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

try:
    import pandas as pd  # type: ignore
except Exception as e:  # pragma: no cover
    sys.stderr.write("ERROR: pandas is required. Install with: pip install pandas\n")
    raise

def _strip(s: Any) -> Any:
    if isinstance(s, str):
        return s.strip()
    return s

def _coerce_int(x: Any) -> Optional[int]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    try:
        return int(x)
    except Exception:
        try:
            # Extract leading integer if present (e.g., "1.", "001", "1a")
            m = re.match(r"\s*(\d+)", str(x))
            if m:
                return int(m.group(1))
        except Exception:
            pass
    return None

def _parse_params(s: Any) -> Dict[str, Any]:
    """
    Try multiple formats:
    1) JSON object string: {"k":"v", "n":1}
    2) Semicolon/comma separated k=v pairs: a=1; b=two, c=3
    3) Empty -> {}
    """
    if s is None:
        return {}
    if isinstance(s, (dict, list)):
        # Already structured (e.g., from previous reads)
        return dict(s) if isinstance(s, dict) else {"_list": s}
    text = str(s).strip()
    if not text:
        return {}

    # Try JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
        else:
            return {"_": obj}
    except Exception:
        pass

    # Try k=v; k2=v2
    parts = re.split(r"[;,]\s*", text)
    out: Dict[str, Any] = {}
    for p in parts:
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = _coerce_scalar(v.strip())
        else:
            # Bare token, collect into a list under "_args"
            out.setdefault("_args", []).append(_coerce_scalar(p.strip()))
    return out

def _coerce_scalar(v: str) -> Any:
    # Try int
    try:
        if re.fullmatch(r"[+-]?\d+", v):
            return int(v)
    except Exception:
        pass
    # Try float
    try:
        if re.fullmatch(r"[+-]?\d*\.\d+([eE][+-]?\d+)?", v) or re.fullmatch(r"[+-]?\d+[eE][+-]?\d+", v):
            return float(v)
    except Exception:
        pass
    # Try booleans
    low = v.lower()
    if low in {"true", "false"}:
        return low == "true"
    if low in {"none", "null"}:
        return None
    return v

@dataclass
class Config:
    input: str = ""
    sheet: Union[str, int, None] = 0
    output: str = "out.json"
    per_case: bool = False

    # Column mappings (case-insensitive match after strip)
    case_id: str = "case"
    step_col: str = "step"
    action_col: str = "action"
    tool_col: Optional[str] = "tool"
    params_col: Optional[str] = "params"
    notes_col: Optional[str] = "notes"

    # Extra columns you want copied through into each step object
    extra_cols: List[str] = field(default_factory=list)

    # Forward-fill these columns (helps with merged cells layouts)
    ffill_cols: List[str] = field(default_factory=lambda: ["case"])

    # Drop rows where *all* of these columns are NaN/empty (clean separators)
    drop_if_all_empty: List[str] = field(default_factory=lambda: ["action", "tool", "params", "notes"])

    # Output shape: "mapping" -> {case_id: {case_id, steps:[...]}},
    # "list" -> [{"case_id":..., "steps":[...]}]
    output_mode: str = "mapping"  # or "list"

    # If step_col missing or unparsable, whether to auto-number within case
    autostep: bool = True

    # If True, attempt fuzzy column inference by common synonyms
    infer_columns: bool = True

    def apply_inference(self, df_cols: List[str]) -> None:
        if not self.infer_columns:
            return

        def find(syns: List[str], default: Optional[str]) -> Optional[str]:
            # match ignoring case and spaces/underscores
            norm = {re.sub(r"[\s_]+", "", c).lower(): c for c in df_cols}
            for s in syns:
                key = re.sub(r"[\s_]+", "", s).lower()
                if key in norm:
                    return norm[key]
            return default

        self.case_id = find(
            ["case", "case_id", "用例", "用例id", "场景", "场景id", "scenario", "id"],
            self.case_id
        ) or self.case_id

        self.step_col = find(
            ["step", "step_index", "步骤", "序号", "顺序", "order", "idx"],
            self.step_col
        ) or self.step_col

        self.action_col = find(
            ["action", "操作", "行为", "描述", "instruction", "指令", "内容"],
            self.action_col
        ) or self.action_col

        self.tool_col = find(
            ["tool", "工具", "函数", "接口", "api", "method"],
            self.tool_col
        )

        self.params_col = find(
            ["params", "参数", "arguments", "args", "payload", "body"],
            self.params_col
        )

        self.notes_col = find(
            ["notes", "备注", "说明", "comment", "commentary"],
            self.notes_col
        )

        if not self.ffill_cols:
            self.ffill_cols = [self.case_id]

def load_config(path: Optional[str]) -> Config:
    if not path:
        return Config()
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    if yaml is None:
        raise RuntimeError("pyyaml not installed. Install with: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cfg = Config(**{k: v for k, v in data.items() if k in Config().__dict__.keys()})
    return cfg

def normalize_dataframe(df, cfg: Config):
    # Strip column names
    df.columns = [str(c).strip() for c in df.columns]
    # Inference
    cfg.apply_inference(list(df.columns))

    # Strip whitespace from string cells
    for c in df.columns:
        df[c] = df[c].map(_strip)

    # Forward fill key cols to handle merged-cell-like layouts
    for c in cfg.ffill_cols:
        if c in df.columns:
            df[c] = df[c].ffill()

    # Drop separator rows where all key content columns are empty
    to_check = [c for c in [cfg.action_col, cfg.tool_col, cfg.params_col, cfg.notes_col] if c and c in df.columns]
    if to_check:
        mask_all_empty = df[to_check].isna().all(axis=1)
        df = df.loc[~mask_all_empty].copy()

    return df

def build_cases(df, cfg: Config):
    # Check mandatory columns
    for col in [cfg.case_id, cfg.action_col]:
        if col not in df.columns:
            raise KeyError(f"Required column missing after inference: {col}")

    # Sort within case by step order if possible
    step_col = cfg.step_col if cfg.step_col in df.columns else None
    if step_col:
        df["_step_idx"] = df[step_col].map(_coerce_int)
    else:
        df["_step_idx"] = None

    # Auto-step if needed
    def assign_autostep(group):
        if group["_step_idx"].isna().all() and cfg.autostep:
            group = group.copy()
            group["_step_idx"] = range(1, len(group) + 1)
        return group

    df = df.groupby(cfg.case_id, dropna=False, sort=False).apply(assign_autostep).reset_index(drop=True)

    # Now sort within each case
    df = df.sort_values(by=[cfg.case_id, "_step_idx"], kind="mergesort")

    # Build case objects
    cases_out = {}
    for case_id, g in df.groupby(cfg.case_id, dropna=False, sort=False):
        steps = []
        for _, row in g.iterrows():
            step_obj = {
                "step": int(row["_step_idx"]) if not pd.isna(row["_step_idx"]) else None,
                "action": row.get(cfg.action_col),
            }
            if cfg.tool_col and cfg.tool_col in g.columns:
                step_obj["tool"] = row.get(cfg.tool_col)
            if cfg.params_col and cfg.params_col in g.columns:
                step_obj["params"] = _parse_params(row.get(cfg.params_col))
            if cfg.notes_col and cfg.notes_col in g.columns:
                note_val = row.get(cfg.notes_col)
                if isinstance(note_val, str) and note_val.strip():
                    step_obj["notes"] = note_val

            # Copy extra columns
            for extra in cfg.extra_cols or []:
                if extra in g.columns:
                    step_obj[extra] = row.get(extra)

            steps.append(step_obj)

        case_obj = {
            "case_id": case_id,
            "num_steps": len(steps),
            "steps": steps,
        }
        cases_out[case_id] = case_obj

    return cases_out

def emit_output(cases: Dict[Any, Dict[str, Any]], cfg: Config) -> Union[Dict, List[Dict]]:
    if cfg.output_mode == "list":
        return [cases[k] for k in cases]
    # default: mapping
    return cases

def write_json(obj, path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def write_per_case(cases: Dict[Any, Dict[str, Any]], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    for cid, obj in cases.items():
        safe = re.sub(r"[^\w\-.]+", "_", str(cid) if cid is not None else "null")
        path = os.path.join(out_dir, f"{safe}.json")
        write_json(obj, path)

def main():
    ap = argparse.ArgumentParser(description="Excel→JSON converter for step tables")
    ap.add_argument("--config", type=str, default=None, help="YAML config path")
    ap.add_argument("--input", type=str, help="Excel file (.xlsx/.xls)")
    ap.add_argument("--sheet", type=str, help="Sheet name or index", default=None)
    ap.add_argument("--output", type=str, help="Output JSON path (or directory if --per-case)", default=None)
    ap.add_argument("--per-case", action="store_true", help="Emit one JSON per case to output directory")

    # Column overrides
    ap.add_argument("--case-id", dest="case_id", type=str, help="Case/Scenario ID column")
    ap.add_argument("--step-col", dest="step_col", type=str, help="Step index column")
    ap.add_argument("--action-col", dest="action_col", type=str, help="Action/Instruction column")
    ap.add_argument("--tool-col", dest="tool_col", type=str, help="Tool/API column")
    ap.add_argument("--params-col", dest="params_col", type=str, help="Params column")
    ap.add_argument("--notes-col", dest="notes_col", type=str, help="Notes column")
    ap.add_argument("--extra-cols", dest="extra_cols", type=str, nargs="*", help="Extra columns to copy into steps")
    ap.add_argument("--ffill-cols", dest="ffill_cols", type=str, nargs="*", help="Columns to forward-fill")
    ap.add_argument("--drop-if-all-empty", dest="drop_if_all_empty", type=str, nargs="*", help="Columns to consider empty-row drop")
    ap.add_argument("--output-mode", dest="output_mode", type=str, choices=["mapping", "list"], help="Output JSON shape")
    ap.add_argument("--no-infer", dest="infer_columns", action="store_false", help="Disable column name inference")
    ap.add_argument("--no-autostep", dest="autostep", action="store_false", help="Disable automatic step numbering")

    args = ap.parse_args()

    cfg = load_config(args.config)
    # CLI overrides
    for k, v in vars(args).items():
        if k in {"config"}:
            continue
        if v is not None:
            setattr(cfg, k, v)

    if not cfg.input and not args.input:
        ap.error("Input Excel file is required (use --input or config input)")
    if cfg.sheet is None and args.sheet is None:
        cfg.sheet = 0

    # Default output if not set
    if not cfg.output:
        cfg.output = "out.json"
    if cfg.per_case:
        # output is a directory
        out_dir = cfg.output
    else:
        out_path = cfg.output

    # Load Excel
    try:
        df = pd.read_excel(cfg.input, sheet_name=cfg.sheet, dtype=object)
    except Exception as e:
        sys.stderr.write(f"ERROR reading Excel: {e}\n")
        sys.exit(2)

    # If multiple sheets returned (dict), pick the first one unless sheet specified
    if isinstance(df, dict):
        if isinstance(cfg.sheet, (int, str)):
            df = df[cfg.sheet]
        else:
            # pick first
            first_key = list(df.keys())[0]
            df = df[first_key]

    df = normalize_dataframe(df, cfg)

    cases = build_cases(df, cfg)

    if cfg.per_case:
        write_per_case(cases, cfg.output)
        print(f"Wrote {len(cases)} case JSON files to: {cfg.output}")
    else:
        obj = emit_output(cases, cfg)
        write_json(obj, cfg.output)
        print(f"Wrote JSON: {cfg.output}  (cases: {len(cases)})")

if __name__ == "__main__":
    main()