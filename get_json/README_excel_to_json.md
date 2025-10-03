# Excel → JSON Converter (for step tables)

This tool converts your Excel step-by-step SOP / test-case tables into a clean JSON format.

1) Install: pip install pandas openpyxl pyyaml

2) Configure: edit config.example.yaml to match your column names and file path.

Common column names it can auto-detect (Chinese/English):
- Case ID: case, case_id, 用例, 场景
- Step: step, 步骤, 序号
- Action: action, 操作, 描述
- Tool: tool, 工具, 接口, api
- Params: params, 参数
- Notes: notes, 备注

3) Run with config:
python excel_to_json.py --config config.example.yaml

Or fully via CLI:
python excel_to_json.py --input ./your_excel.xlsx --sheet 0 --output out.json --case-id case --step-col step --action-col action --tool-col tool --params-col params --notes-col notes

4) Param Parsing
- JSON string: {"k":"v","n":1} → parsed as an object
- k=v pairs: a=1; b=two, c=3 → parsed to {a:1,b:"two",c:3}
- Bare tokens: click; wait(2) → {"_args":["click","wait(2)"]}

5) Output Shapes
- mapping (default): { "LoginCase": { "case_id": "LoginCase", "num_steps": 2, "steps": [ ... ] } }
- list: [ {"case_id": "LoginCase", "num_steps": 2, "steps": [ ... ]} ]

6) Tips
- If your Excel uses merged cells for the case ID, the script forward-fills it downward.
- If your step column is missing, set autostep: true to auto-number.
- Use per_case: true to emit one JSON per case into a directory.

7) Troubleshooting
- If it says a required column is missing, enable infer_columns: true or set the exact names in the config.
- If reading .xlsx fails, ensure openpyxl is installed.