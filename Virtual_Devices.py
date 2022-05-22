import paho.mqtt.client as mqtt
from random import uniform
import threading
import json
import time

V_HUMI = 0
V_TEMP = 0
V_AIRP = 0

AIRPS = False
HUMIS = False

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("completely connected")
    else:
        print("Bad connection Returned code=", rc)
def on_disconnect(client, userdata, flags, rc=0):
    print(str(rc))
def on_publish(client, userdata, mid):
    #print("In on_pub callback mid= ", mid)
    pass

def ack_humi(client, userdata, msg):
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    print("     HUMI DEVICE ACK", json_data)
def ack_air(client, userdata, msg):
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    print("     AIRP DEVICE ACK", json_data)

def control_humi(client, userdata, msg):
    global AIRPS, HUMIS
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    #time.sleep(7)
    if "OnOff" in json_data.keys():
        if json_data["OnOff"] == "On":
            HUMIS = True
        elif json_data["OnOff"] == "Off":
            HUMIS = False
def control_air(client, userdata, msg):
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    #time.sleep(7)
    if "OnOff" in json_data.keys():
        if json_data["OnOff"] == "On":
            AIRPS = True
        elif json_data["OnOff"] == "Off":
            AIRPS = False

# 새로운 클라이언트 생성
client = mqtt.Client()

# 콜백 함수 설정 
# on_connect(브로커에 접속), on_disconnect(브로커에 접속중료), on_publish(메세지 발행)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_publish = on_publish

# HiveMQ를 사용합니다.
# client.connect('broker.mqttdashboard.com', 1883)
client.connect('broker.mqttdashboard.com', 1883)
# ACK RESPONSE
client.subscribe("UNIQUEHEADER/CONTROLACK/#", 2)
client.message_callback_add("UNIQUEHEADER/CONTROLACK/Humi", ack_humi)
client.message_callback_add("UNIQUEHEADER/CONTROLACK/Air", ack_air)
# CONTROL RESPONSE
client.subscribe("GOLDILOCKS/CONTROL/#", 2)
client.message_callback_add("GOLDILOCKS/CONTROL/HUMI", control_humi)
client.message_callback_add("GOLDILOCKS/CONTROL/AIR", control_air)
client.loop_start()

def VAL_SENDER():
    global V_HUMI, V_TEMP, V_AIRP, AIRPS, HUMIS
    while True:
        # Device
        json_object = {"OnOff" : "On" if HUMIS == True else "Off"}
        json_string = json.dumps(json_object)
        client.publish('UNIQUEHEADER/CONTROLACK/Humi', json_string, 2)
        json_object = {"OnOff" : "On" if AIRPS == True else "Off"}
        json_string = json.dumps(json_object)
        client.publish('UNIQUEHEADER/CONTROLACK/Air', json_string, 2)
        # Sensor
        json_object = {"Humi" : V_HUMI}
        json_string = json.dumps(json_object)
        client.publish('UNIQUEHEADER/SENSOR/Humi', json_string, 0)
        json_object = {"Temp" : V_TEMP}
        json_string = json.dumps(json_object)
        client.publish('UNIQUEHEADER/SENSOR/Temp', json_string, 0)
        json_object = {"AirP" : V_AIRP}
        json_string = json.dumps(json_object)
        client.publish('UNIQUEHEADER/SENSOR/AirP', json_string, 0)

        print("SEND HUMI {:02f} TEMP {:02f} AIRP {:02f}".format(V_HUMI, V_TEMP, V_AIRP))
        time.sleep(4)

def KEY_INPUT():
    global V_HUMI, V_TEMP, V_AIRP
    while True:
        T, V = input().split()
        if T in "Hh":
            V_HUMI = int(V)
            print("             HUMI {:02f}".format(V_HUMI))
        elif T in "Tt":
            V_TEMP = int(V)
            print("             TEMP {:02f}".format(V_TEMP))
        elif T in "Aa":
            V_AIRP = int(V)
            print("             AIRP {:02f}".format(V_AIRP))

if __name__ == "__main__":
    vs = threading.Thread(target=VAL_SENDER)
    vs.daemon = True
    vs.start()
    ki = threading.Thread(target=KEY_INPUT)
    ki.daemon = True
    ki.start()

    while True:
        time.sleep(1)

    # 연결 종료
    client.loop_stop()
    client.disconnect()

# Case2
# 둘다 off
# A 0
# H 60
# T 22

# 공기청정기 > 가습기 우선순위 보여주기
# case3
# 공기청정기 on
# A 100
# H 20
# T 22

# Case1
# 공기정청기 off, 가습기 on
# A 60
# H 20
# T 22

# Case2
# 둘다 off 되면서 끝
# A 60
# H 60
# T 22
