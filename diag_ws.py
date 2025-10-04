import inspect, sys
import websockets
print("websockets file:", websockets.__file__)
print("websockets version:", websockets.__version__)
print("connect signature:", inspect.signature(websockets.connect))

# 试着直接调用（不用真的连）
from websockets.client import connect as client_connect
print("client.connect signature:", inspect.signature(client_connect))
