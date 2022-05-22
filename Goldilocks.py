# Communicate With User
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler # pip install python-telegram-bot
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Bot
# Message TimeStamp
import time
from time import localtime
# Get Sensor Value by MQTT
import paho.mqtt.client as mqtt # pip3 install paho-mqtt
# GPS API
import requests
import json
# Weather API
from pyowm import OWM # pip3 install pyowm
# for Multi Threading
# Thread list [Telegram, API, Sensor(MQTT)]
import threading
import matplotlib.pyplot as plt

#==============화면 => 메시지 / 버튼들==============#
# home => 디바이스상태, 현제방상태 / info, on&off, 새로고침, 알림설정
# info => 명령어설명 / home
# on&off => 디바이스상태표시, 현제방상태 / 가습기on, 가습기off, 공기청정기on, 공기청정기off, home
    # 하나on 바로 on 둘다on warning
    # warning => 경고메시지 / 그래도키겠습니다, 그럼안킬게용
# 새로고침 => 메인 화면 새로고침 / info, on&off, 새로고침, 알림설정
# 알림설정 => 불쾌지수그래프 어려우면 현제시간으로만, 자동제어알림상태 / 자동제어알림on, 자동제어알림off, home

# ALL BUTTONS
# info, on&off, 새로고침, 알림설정, home, 가습기on, 가습기off, 공기청정기on, 공기청정기off,
# 그래도진행, 그럼안켤게요, 자동제어알림on, 자동제어알림off

#====================GLOBALS====================#
# Message Info
MESSAGE_LOCK = threading.Lock()
OPEN_CHAT_ID = []   #[chat_id, photo_id, prev_alarm_id, remote_id]
TELEGRAM_BOT = Bot('YOUR KEY HERE')
MQTT_CLIENT = mqtt.Client()     # MQTT Client

# Device, Alarm Status
STATUS_LOCK = threading.Lock()
DEVICE_STATUS = [False, False]  # [Humidifier_ON, AirCleaner_On]
ALARM_STATUS = False            # Auto Control Alarm On/Off.
# Pending on/off command.
PENDING = None

# Sensor Data Storage.
SENSOR_VALUE_LOCK = threading.Lock()
SENSOR_HUMI_BUFFER = [0.0]
SENSOR_TEMP_BUFFER = [0.0]
SENSOR_AIRP_BUFFER = [0.0]
SENSOR_HUMI_LIST = [0.0 for _ in range(72)]   # 12h / 10m = 72
SENSOR_TEMP_LIST = [0.0 for _ in range(72)] 
SENSOR_AIRP_LIST = [0.0 for _ in range(72)] 
# API Data Storage.
API_VALUE_LOCK    = threading.Lock()
API_HUMI_LIST = [0.0 for _ in range(72)]       # 12h / 10m = 72
API_TEMP_LIST = [0.0 for _ in range(72)] 
API_AIRP_LIST = [0.0 for _ in range(72)] 
# Device Control Time
HUMI_OFF_TICK_COUNT = 0
SUDO_CONTROL_TICK_COUNT = 100

# 간단하게 메뉴를 만들어주는 함수.
def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    # menu 
    # [[header_buttons]
    #  [1,   2,   3   ] => n_cols만큼씩 끊어서 []화 시켜서 row를 만든다.
    #  [4,   5,   6   ]
    #  [footer_buttons]]
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu

# 버튼을 만들어주는 함수.
def build_button(text_list): # make button list
    button_list = []
    for text in text_list :
        button_list.append(InlineKeyboardButton(text, callback_data=text))
    return button_list

# None     : None
# "i", "I" : [YYYY, MM, DD, hh, mm, ss]
# "t", "T" : YYYY-MM-DD hh:mm:ss 
def GetYMDhms(format = None):
    tm = localtime()
    if format == None:
        return None
    elif format == 't' or format == 'T':
        return "{0}-{1}-{2} {3}:{4}:{5}".format(tm.tm_year, tm.tm_mon,
                tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec)
    elif format == 'i' or format == 'I':
        return [tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec]

# [lat, lon]
def GetGPS():
    url = 'http://ip-api.com/json'
    data = requests.get(url)
    res = data.json()
    #print(res)
    return [res["lat"], res["lon"]]

# return in list form
# detailed_status   'clouds'
# wind              {'speed': 4.6, 'deg': 330}
# humidity          87
# temperature       {'temp_max': 10.5, 'temp': 9.7, 'temp_min': 9.0}
# rain              {}
# heat_index        None
# clouds            75
def API_Curr_Weather():
    LatLon = GetGPS()
    owm = OWM('YOUT KEY HERE')
    w_mgr = owm.weather_manager()
    obs = w_mgr.weather_at_coords(LatLon[0], LatLon[1])
    weather = obs.weather
    return [weather.detailed_status, weather.wind(), weather.humidity,
        weather.temperature('celsius'), weather.rain, weather.heat_index, weather.clouds]

# return in list form
# co, no, no2, o3, so2, pm2_5, pm10, nh3
def API_Curr_AirP():
    LatLon = GetGPS()
    owm = OWM('YOUT KEY HERE')
    ap_mgr = owm.airpollution_manager()
    air_status = ap_mgr.air_quality_at_coords(LatLon[0], LatLon[1])
    return [air_status.co, air_status.no, air_status.no2, air_status.o3,
        air_status.so2, air_status.pm2_5, air_status.pm10, air_status.nh3]

# Get Next 24h forecast by 3h
# ["YYYY-MM-DD hh:mm:ss+00:00", weather]
def API_Weather_Forecast():
    LatLon = GetGPS()
    owm = OWM('YOUT KEY HERE')
    wf_mgr = owm.weather_manager()
    three_h_forecaster = wf_mgr.forecast_at_coords(LatLon[0], LatLon[1], '3h')
    from pyowm.utils import timestamps
    three_H = [0, 3, 6, 9, 12, 15, 18, 21]
    res = []
    for Hour in three_H:
        if GetYMDhms("i")[3] < Hour:
            Today_T = str(timestamps.now()).split()[0] + " {0:02d}:00:00+00:00".format(Hour)
            weather = three_h_forecaster.get_weather_at(Today_T)
            res.append([Today_T, weather])
    for Hour in three_H:
        if Hour < GetYMDhms("i")[3]:
            Today_T = str(timestamps.tomorrow()).split()[0] + " {0:02d}:00:00+00:00".format(Hour)
            weather = three_h_forecaster.get_weather_at(Today_T)
            res.append([Today_T, weather])
    return res

# Screens..
def HomeScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST

    button_list = build_button(["Info", "on&off", "새로고침", "알림설정"])
    show_markup = InlineKeyboardMarkup(build_menu(button_list, 2))
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    # Device Status
    while STATUS_LOCK.locked():
        continue
    STATUS_LOCK.acquire()
    l3  = " 디바이스 상태\n"
    l4  = " 가습기 : {}, 공기청정기 : {}\n".format(
        "OFF" if DEVICE_STATUS[0] == False else "ON ", 
        "OFF" if DEVICE_STATUS[1] == False else "ON ")
    STATUS_LOCK.release()

    # Sensor Values
    while SENSOR_VALUE_LOCK.locked():
        continue
    SENSOR_VALUE_LOCK.acquire()
    l5  = " 현제 날씨\n"
    l6  = " Sensor_Humi : {:.2f}\n".format(SENSOR_HUMI_BUFFER[-1])
    l7  = " Sensor_Temp : {:.2f}\n".format(SENSOR_TEMP_BUFFER[-1])
    l8  = " Sensor_AirP : {:.2f}\n".format(SENSOR_AIRP_BUFFER[-1])
    SENSOR_VALUE_LOCK.release()

    # API Values
    while API_VALUE_LOCK.locked():
        continue
    API_VALUE_LOCK.acquire()
    l9  = " API_Humi    : {:.2f}\n".format(API_HUMI_LIST[-1])
    l10 = " API_Temp    : {:.2f}\n".format(API_TEMP_LIST[-1])
    #l11 = " API_AirP    : {:.2f}\n".format(API_AIRP_LIST[-1])
    API_VALUE_LOCK.release()

    disp_text = l1 + l2 + l3 + l4 + l5 + l6 + l7 + l8 + l9 + l10# + l11
    return [show_markup, disp_text]

def InfoScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    button_list = build_button(["home"])
    show_markup = InlineKeyboardMarkup(build_menu(button_list, 2))
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    l3 = " /start 로 새로운 리모컨 만들기\n"
    l4 = " 추가 내용...\n"
    disp_text = l1 + l2 + l3 + l4
    return [show_markup, disp_text]

def OnOffScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST

    button_list = build_button(["가습기on", "가습기off", "공기청정기on", "공기청정기off", "home"])
    show_markup = InlineKeyboardMarkup(build_menu(button_list, 2))
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    # Device Status
    while STATUS_LOCK.locked():
        continue
    STATUS_LOCK.acquire()
    l3  = " 디바이스 상태\n"
    l4  = " 가습기 : {}, 공기청정기 : {}\n".format(
        "OFF" if DEVICE_STATUS[0] == False else "ON ", 
        "OFF" if DEVICE_STATUS[1] == False else "ON ")
    STATUS_LOCK.release()

    # Sensor Values
    while SENSOR_VALUE_LOCK.locked():
        continue
    SENSOR_VALUE_LOCK.acquire()
    l5  = " 현제 날씨\n"
    l6  = " Sensor_Humi : {:.2f}\n".format(SENSOR_HUMI_BUFFER[-1])
    l7  = " Sensor_Temp : {:.2f}\n".format(SENSOR_TEMP_BUFFER[-1])
    l8  = " Sensor_AirP : {:.2f}\n".format(SENSOR_AIRP_BUFFER[-1])
    SENSOR_VALUE_LOCK.release()

    # API Values
    while API_VALUE_LOCK.locked():
        continue
    API_VALUE_LOCK.acquire()
    curr_weather = API_Curr_Weather()
    l9  = " API_Humi    : {:.2f}\n".format(API_HUMI_LIST[-1])
    l10 = " API_Temp    : {:.2f}\n".format(API_TEMP_LIST[-1])
    #l11 = " API_AirP    : {:.2f}\n".format(API_AIRP_LIST[-1])
    API_VALUE_LOCK.release()

    disp_text = l1 + l2 + l3 + l4 + l5 + l6 + l7 + l8 + l9 + l10# + l11
    return [show_markup, disp_text]

def WarningScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    button_list = build_button(["그래도진행", "그럼안켤게요"])
    show_markup = InlineKeyboardMarkup(build_menu(button_list, 2))
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    l3 = " WARNING\n"
    l4 = " 공기청정기와 가습기를 동시에 작동시\n"
    l5 = " 문제가 발생할 수 있습니다.\n"
    disp_text = l1 + l2 + l3 + l4 + l5
    return [show_markup, disp_text]

def AlreadyScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    button_list = build_button(["확인"])
    show_markup = InlineKeyboardMarkup(build_menu(button_list, 2))
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    # Pending Info
    while STATUS_LOCK.locked():
        continue
    STATUS_LOCK.acquire()
    l3 = " 이미 {} 상태 입니다.\n".format(PENDING)
    STATUS_LOCK.release()

    disp_text = l1 + l2 + l3
    return [show_markup, disp_text]

def AlarmScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    button_list = build_button(["불쾌지수그래프", "자동제어알림on", "자동제어알림off", "home"])
    show_markup = InlineKeyboardMarkup([[button_list[0]], [button_list[1], button_list[2]], [button_list[3]]])
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    l3 = " 자동제어시 알람을 끄고 켭니다.\n"
    # Alarm Status
    while STATUS_LOCK.locked():
        continue
    STATUS_LOCK.acquire()
    l4 = " 현제 알림 상태 : {}".format("OFF" if ALARM_STATUS == False else "On")
    STATUS_LOCK.release()

    disp_text = l1 + l2 + l3 + l4
    return [show_markup, disp_text]

def GraphScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    button_list = build_button(["OK"])
    show_markup = InlineKeyboardMarkup(build_menu(button_list, 1))
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    l3 = " 실외, 실내 불쾌지수 그래프입니다.\n"

    disp_text = l1 + l2 + l3
    return [show_markup, disp_text]

def WaitingScreen():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    l1 = "==============================\n"
    l2 = GetYMDhms("t")+"\n"
    # Alarm Status
    while STATUS_LOCK.locked():
        continue
    STATUS_LOCK.acquire()
    l3 = " {} 명령 실행중입니다. ".format(PENDING)
    STATUS_LOCK.release()

    disp_text = l1 + l2 + l3
    return [None, disp_text]

# 채팅방이 열리면 /start command가 들어오는데 그때 실행되는 함수.
def start_command(update, context):
    print("callback : start")
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    
    # delete previous message windows
    while MESSAGE_LOCK.locked():
        continue
    MESSAGE_LOCK.acquire()
    if len(OPEN_CHAT_ID) == 4:
        for idx in range(1, 4):
            context.bot.delete_message(
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[idx])

    i_message = update.message.reply_photo(
        photo = open("/home/pi/Desktop/Goldilocks/Logo.png", "rb"))
    
    a_message = update.message.reply_text(
        text="경고또는 알림 메시지가 표시될 창")

    homescreen = HomeScreen()
    t_message = update.message.reply_text(
        reply_markup=homescreen[0],
        text=homescreen[1])

    OPEN_CHAT_ID = [update.message.chat_id, i_message.message_id,
                    a_message.message_id, t_message.message_id]
    MESSAGE_LOCK.release()

"""
context.bot.edit_message_media(
    media = InputMediaPhoto(open("bbb.gif", "rb")),
    chat_id=OPEN_CHAT_ID[0],
    message_id=OPEN_CHAT_ID[1])
context.bot.edit_message_text(
    text = "",
    chat_id=OPEN_CHAT_ID[0],
    message_id=OPEN_CHAT_ID[2])
context.bot.edit_message_text(
    reply_markup= [],
    text = "",
    chat_id=OPEN_CHAT_ID[0],
    message_id=OPEN_CHAT_ID[3])
"""
def callback(update, context):
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    # Time Counter
    global HUMI_OFF_TICK_COUNT, SUDO_CONTROL_TICK_COUNT

    data_selected = update.callback_query.data
    print("callback : ", data_selected)

    # send reply
    while MESSAGE_LOCK.locked():
        continue
    MESSAGE_LOCK.acquire()

    if data_selected in ["home", "새로고침"]:
        hoomescreen = HomeScreen()
        context.bot.edit_message_text(
            reply_markup= hoomescreen[0],
            text = hoomescreen[1],
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[3])
    # Info 버튼 관리 그래프 표시 화면으로 사용할것
    elif data_selected == "Info":
        infoscreen = InfoScreen()
        context.bot.edit_message_text(
            reply_markup= infoscreen[0],
            text = infoscreen[1],
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[3])
    elif data_selected == "on&off":
        onoffscreen = OnOffScreen()
        context.bot.edit_message_text(
            reply_markup= onoffscreen[0],
            text = onoffscreen[1],
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[3])
    elif data_selected == "가습기on":
        PENDING = data_selected
        if DEVICE_STATUS == [True, True]:
            alreadyscreen = AlreadyScreen()
            context.bot.edit_message_text(
                reply_markup= alreadyscreen[0],
                text = alreadyscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS == [True, False]:
            alreadyscreen = AlreadyScreen()
            context.bot.edit_message_text(
                reply_markup= alreadyscreen[0],
                text = alreadyscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS == [False, True]:
            warningscreen = WarningScreen()
            context.bot.edit_message_text(
                reply_markup= warningscreen[0],
                text = warningscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS == [False, False]:
            DEVICE_STATUS[0] = "PENDING"
            SUDO_CONTROL_TICK_COUNT = 0
            waitingscreen = WaitingScreen()
            context.bot.edit_message_text(
                reply_markup= waitingscreen[0],
                text = waitingscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
            while DEVICE_STATUS[0] != True:
                print("가습기on")
                json_object = {"OnOff" : "On"}
                json_string = json.dumps(json_object)
                MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/HUMI", json_string, 2)
                time.sleep(5)
            onoffscreen = OnOffScreen()
            context.bot.edit_message_text(
                reply_markup= onoffscreen[0],
                text = onoffscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        else:
            DEVICE_STATUS[0] = False
    elif data_selected == "가습기off":
        PENDING = data_selected
        if DEVICE_STATUS[0] == True:
            DEVICE_STATUS[0] = "PENDING"
            SUDO_CONTROL_TICK_COUNT = 0
            waitingscreen = WaitingScreen()
            context.bot.edit_message_text(
                reply_markup= waitingscreen[0],
                text = waitingscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
            while DEVICE_STATUS[0] != False:
                print("가습기off")
                json_object = {"OnOff" : "Off"}
                json_string = json.dumps(json_object)
                MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/HUMI", json_string, 2)
                time.sleep(5)
            onoffscreen = OnOffScreen()
            context.bot.edit_message_text(
                reply_markup= onoffscreen[0],
                text = onoffscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS[0] == False:
            alreadyscreen = AlreadyScreen()
            context.bot.edit_message_text(
                reply_markup= alreadyscreen[0],
                text = alreadyscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        else:
            DEVICE_STATUS[0] = False
    elif data_selected == "공기청정기on":
        PENDING = data_selected
        if DEVICE_STATUS == [True, True]:
            alreadyscreen = AlreadyScreen()
            context.bot.edit_message_text(
                reply_markup= alreadyscreen[0],
                text = alreadyscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS == [True, False]:
            warningscreen = WarningScreen()
            context.bot.edit_message_text(
                reply_markup= warningscreen[0],
                text = warningscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS == [False, True]:
            alreadyscreen = AlreadyScreen()
            context.bot.edit_message_text(
                reply_markup= alreadyscreen[0],
                text = alreadyscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS == [False, False]:
            DEVICE_STATUS[1] = "PENDING"
            SUDO_CONTROL_TICK_COUNT = 0
            waitingscreen = WaitingScreen()
            context.bot.edit_message_text(
                reply_markup= waitingscreen[0],
                text = waitingscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
            while DEVICE_STATUS[1] != True:
                print("공기청정기on")
                json_object = {"OnOff" : "On"}
                json_string = json.dumps(json_object)
                MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/AIR", json_string, 2)
                time.sleep(5)
            onoffscreen = OnOffScreen()
            context.bot.edit_message_text(
                reply_markup= onoffscreen[0],
                text = onoffscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        else:
            DEVICE_STATUS[1] = False
    elif data_selected == "공기청정기off":
        PENDING = data_selected
        if DEVICE_STATUS[1] == True:
            DEVICE_STATUS[1] = "PENDING"
            SUDO_CONTROL_TICK_COUNT = 0
            waitingscreen = WaitingScreen()
            context.bot.edit_message_text(
                reply_markup= waitingscreen[0],
                text = waitingscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
            while DEVICE_STATUS[1] != False:
                print("공기청정기off")
                json_object = {"OnOff" : "Off"}
                json_string = json.dumps(json_object)
                MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/AIR", json_string, 2)
                time.sleep(5)
            onoffscreen = OnOffScreen()
            context.bot.edit_message_text(
                reply_markup= onoffscreen[0],
                text = onoffscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif DEVICE_STATUS[1] == False:
            alreadyscreen = AlreadyScreen()
            context.bot.edit_message_text(
                reply_markup= alreadyscreen[0],
                text = alreadyscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        else:
            DEVICE_STATUS[1] = False
    elif data_selected == "그래도진행":
        SUDO_CONTROL_TICK_COUNT = 0
        if PENDING == "가습기on":
            DEVICE_STATUS[0] = "PENDING"
            waitingscreen = WaitingScreen()
            context.bot.edit_message_text(
                reply_markup= waitingscreen[0],
                text = waitingscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
            while DEVICE_STATUS[0] != True:
                print("가습기on")
                json_object = {"OnOff" : "On"}
                json_string = json.dumps(json_object)
                MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/HUMI", json_string, 2)
                time.sleep(5)
            onoffscreen = OnOffScreen()
            context.bot.edit_message_text(
                reply_markup= onoffscreen[0],
                text = onoffscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif PENDING == "공기청정기on":
            DEVICE_STATUS[1] = "PENDING"
            waitingscreen = WaitingScreen()
            context.bot.edit_message_text(
                reply_markup= waitingscreen[0],
                text = waitingscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
            while DEVICE_STATUS[1] != True:
                print("공기청정기on")
                json_object = {"OnOff" : "On"}
                json_string = json.dumps(json_object)
                MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/AIR", json_string, 2)
                time.sleep(5)
            onoffscreen = OnOffScreen()
            context.bot.edit_message_text(
                reply_markup= onoffscreen[0],
                text = onoffscreen[1],
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[3])
        elif PENDING in ["가습기off", "공기청정기off"]:
            print("ERROR off on PENDING")
        else:
            print("ERROR undefined on PENDING")
    elif data_selected == "그럼안켤게요":
        onoffscreen = OnOffScreen()
        context.bot.edit_message_text(
            reply_markup= onoffscreen[0],
            text = onoffscreen[1],
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[3])
    elif data_selected in ["OK", "알림설정", "자동제어알림on", "자동제어알림off"]:
        if data_selected == "OK":
            context.bot.edit_message_media(
                media = InputMediaPhoto(open("/home/pi/Desktop/Goldilocks/Logo.png", "rb")),
                chat_id=OPEN_CHAT_ID[0],
                message_id=OPEN_CHAT_ID[1])
        elif data_selected == "알림설정":
            pass
        elif data_selected == "자동제어알림on":
            ALARM_STATUS = True
        elif data_selected == "자동제어알림off":
            ALARM_STATUS = False
        alarmscreen = AlarmScreen()
        context.bot.edit_message_text(
        reply_markup= alarmscreen[0],
            text = alarmscreen[1],
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[3])
    elif data_selected == "불쾌지수그래프":
        pass
        # Send Graph
        context.bot.edit_message_media(
            media = InputMediaPhoto(open("/home/pi/Desktop/Goldilocks/justRight.png", "rb")),
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[1])
        graphscreen = GraphScreen()
        context.bot.edit_message_text(
            reply_markup= graphscreen[0],
            text = graphscreen[1],
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[3])
    elif data_selected == "확인":
        onoffscreen = OnOffScreen()
        context.bot.edit_message_text(
            reply_markup= onoffscreen[0],
            text = onoffscreen[1],
            chat_id=OPEN_CHAT_ID[0],
            message_id=OPEN_CHAT_ID[3])

    MESSAGE_LOCK.release()

# Telegram for User Control
def StartTelegram():
    my_token = 'YOUT KEY HERE'
    updater = Updater(my_token, use_context=True)

    # "/get" 을 명령으로 받으면 get_command 함수를 실행한다.
    updater.dispatcher.add_handler(CommandHandler("start", start_command))
    # callback 함수를 사용해서 버튼을 통해 들어온 명령을 처리한다.
    updater.dispatcher.add_handler(CallbackQueryHandler(callback))

    updater.start_polling(timeout=1, drop_pending_updates=True)

# MQTT Callback Functions..
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("connected OK")
    else:
        print("Bad connection Returned code=", rc)
def on_disconnect(client, userdata, flags, rc=0):
    print(str(rc))
def on_subscribe(client, userdata, mid, granted_qos):
    print("subscribed: " + str(mid) + " " + str(granted_qos))

# Get Sensor Data From Sensor Device
def Humi_Sensor_Message(client, userdata, msg):
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    while SENSOR_VALUE_LOCK.locked():
        continue
    SENSOR_VALUE_LOCK.acquire()
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    print("          HUMI SENSOR : ", json_data)
    #print(json_data)
    if "Humi" in json_data.keys():
        #print(json_data["Humi"])
        SENSOR_HUMI_BUFFER.append(float(json_data["Humi"]))
        #print("     HUMI : {}".format(json_data["Humi"]))
    SENSOR_VALUE_LOCK.release()
def Temp_Sensor_Message(client, userdata, msg):
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    while SENSOR_VALUE_LOCK.locked():
        continue
    SENSOR_VALUE_LOCK.acquire()
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    print("          TEMP SENSOR : ", json_data)
    #print(json_data)
    if "Temp" in json_data.keys():
        #print(json_data["Temp"])
        SENSOR_TEMP_BUFFER.append(float(json_data["Temp"]))
        #print("     TEMP : {}".format(json_data["Temp"]))
    SENSOR_VALUE_LOCK.release()
def AirP_Sensor_Message(client, userdata, msg):
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    while SENSOR_VALUE_LOCK.locked():
        continue
    SENSOR_VALUE_LOCK.acquire()
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    print("          AIRP SENSOR : ", json_data)
    #print(json_data)
    if "AirP" in json_data.keys():
        #print(json_data["AirP"])
        SENSOR_AIRP_BUFFER.append(float(json_data["AirP"]))
        #print("     AIRP : {}".format(json_data["AirP"]))
    SENSOR_VALUE_LOCK.release()
# Get Device On Off ACK From Controler
def Humi_Control_message(client, userdata, msg):
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    while STATUS_LOCK.locked():
        continue
    STATUS_LOCK.acquire()
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    print("                    HUMI ACK : ", json_data)
    if "OnOff" in json_data.keys():
        if json_data["OnOff"] == "On":
            DEVICE_STATUS[0] = True
        elif json_data["OnOff"] == "Off":
            DEVICE_STATUS[0] = False
        elif json_data["OnOff"] == "ERROR":
            print("Device Control Humi ERROR")
    STATUS_LOCK.release()
def AirP_Control_message(client, userdata, msg):
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    while STATUS_LOCK.locked():
        continue
    STATUS_LOCK.acquire()
    json_data = json.loads(str(msg.payload.decode("utf-8")))
    print("                    AIRP ACK : ", json_data)
    if "OnOff" in json_data.keys():
        if json_data["OnOff"] == "On":
            DEVICE_STATUS[1] = True
        elif json_data["OnOff"] == "Off":
            DEVICE_STATUS[1] = False
        elif json_data["OnOff"] == "ERROR":
            print("Device Control AirP ERROR")
    STATUS_LOCK.release()

# Start MQTT Communication
def StartMQTT():
    global MQTT_CLIENT
    # 콜백 함수 설정
    # on_connect(브로커에 접속), on_disconnect(브로커에 접속중료), 
    # on_subscribe(topic 구독), on_message(발행된 메세지가 들어왔을 때)
    MQTT_CLIENT.on_connect = on_connect
    MQTT_CLIENT.on_disconnect = on_disconnect
    MQTT_CLIENT.on_subscribe = on_subscribe
    # 특정 토픽의 메시지를 디바이스가 보낼 경우 처리하는 함수에 콜백 설정을 해준다.
    MQTT_CLIENT.message_callback_add("UNIQUEHEADER/SENSOR/Humi", Humi_Sensor_Message)
    MQTT_CLIENT.message_callback_add("UNIQUEHEADER/SENSOR/Temp", Temp_Sensor_Message)
    MQTT_CLIENT.message_callback_add("UNIQUEHEADER/SENSOR/AirP", AirP_Sensor_Message)
    MQTT_CLIENT.message_callback_add("UNIQUEHEADER/CONTROLACK/Humi", Humi_Control_message)
    MQTT_CLIENT.message_callback_add("UNIQUEHEADER/CONTROLACK/Air", AirP_Control_message)

    # HiveMQ를 사용합니다.
    MQTT_CLIENT.connect('broker.mqttdashboard.com', 1883)
    # 해당 토픽에 구독해서 메시지를 확인합니다.
    MQTT_CLIENT.subscribe("UNIQUEHEADER/SENSOR/#", 0)
    MQTT_CLIENT.subscribe("UNIQUEHEADER/CONTROLACK/#", 2)
    MQTT_CLIENT.loop_forever()

# Store Data to List
def Save_API():
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    while True:
        # Wait for my turn
        while API_VALUE_LOCK.locked():
            continue
        API_VALUE_LOCK.acquire()
        # Save API Value
        Hourly_Weather = API_Curr_Weather()
        API_HUMI_LIST.append(float(Hourly_Weather[2]))
        API_TEMP_LIST.append(float(Hourly_Weather[3]['temp']))
        #API_AIRP_LIST.append(None)
        if 72 < len(API_HUMI_LIST):
            API_HUMI_LIST = API_HUMI_LIST[-72:]
        if 72 < len(API_TEMP_LIST):
            API_TEMP_LIST = API_TEMP_LIST[-72:]
        #if 72 < len(API_AIRP_LIST):
        #    API_AIRP_LIST = API_AIRP_LIST[-72]
        API_VALUE_LOCK.release()
        # Run Every Hour..
        tm = localtime()
        time.sleep(60 - tm.tm_sec)
def Save_Sensor():
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST

    while True:
        # Wait for my turn
        while SENSOR_VALUE_LOCK.locked():
            continue
        SENSOR_VALUE_LOCK.acquire()
        # Save Sensor Value
        SENSOR_HUMI_LIST.append(sum(SENSOR_HUMI_BUFFER)/len(SENSOR_HUMI_BUFFER))
        SENSOR_TEMP_LIST.append(sum(SENSOR_TEMP_BUFFER)/len(SENSOR_TEMP_BUFFER))
        SENSOR_AIRP_LIST.append(sum(SENSOR_AIRP_BUFFER)/len(SENSOR_AIRP_BUFFER))
        SENSOR_HUMI_BUFFER = [SENSOR_HUMI_LIST[-1]]
        SENSOR_TEMP_BUFFER = [SENSOR_TEMP_LIST[-1]]
        SENSOR_AIRP_BUFFER = [SENSOR_AIRP_LIST[-1]]
        if 72 < len(SENSOR_HUMI_LIST):
            SENSOR_HUMI_LIST = SENSOR_HUMI_LIST[-72:]
        if 72 < len(SENSOR_TEMP_LIST):
            SENSOR_TEMP_LIST = SENSOR_TEMP_LIST[-72:]
        if 72 < len(SENSOR_AIRP_LIST):
            SENSOR_AIRP_LIST = SENSOR_AIRP_LIST[-72:]
        SENSOR_VALUE_LOCK.release()
        # Run Every Hour..
        tm = localtime()
        time.sleep(60 - tm.tm_sec)

# 
def Auto_Device_Control():
    # Communication Info
    global MESSAGE_LOCK, OPEN_CHAT_ID, TELEGRAM_BOT, MQTT_CLIENT
    # Device, Alarm Status
    global STATUS_LOCK, DEVICE_STATUS, ALARM_STATUS, PENDING
    # API Value
    global API_VALUE_LOCK
    global API_HUMI_LIST, API_TEMP_LIST, API_AIRP_LIST
    # Sensor Value
    global SENSOR_VALUE_LOCK
    global SENSOR_HUMI_BUFFER, SENSOR_TEMP_BUFFER, SENSOR_AIRP_BUFFER
    global SENSOR_HUMI_LIST, SENSOR_TEMP_LIST, SENSOR_AIRP_LIST
    # Time Counter
    global HUMI_OFF_TICK_COUNT, SUDO_CONTROL_TICK_COUNT
    
    tm = localtime()
    time.sleep(70 - tm.tm_sec)
    
    while True:
        # Run Every 10 min + 10sec
        #print(DEVICE_STATUS, ALARM_STATUS, PENDING)
        #print(API_HUMI_LIST[-1], API_TEMP_LIST[-1])#, API_AIRP_LIST[-1])
        #print(SENSOR_HUMI_LIST[-1], SENSOR_TEMP_LIST[-1], SENSOR_AIRP_LIST[-1])
        #print(HUMI_OFF_TICK_COUNT, SUDO_CONTROL_TICK_COUNT)
        
        # send reply
        while MESSAGE_LOCK.locked():
            continue
        MESSAGE_LOCK.acquire()

        if DEVICE_STATUS[0] == False:
            HUMI_OFF_TICK_COUNT += 1
        else:
            HUMI_OFF_TICK_COUNT = 0
        MinHumi = 30
        MaxHumi = 0

        # T 15 = H 70
        # T 19 = H 60
        # T 22 = H 50
        # T 24 = H 40

        if SENSOR_TEMP_LIST[-1] < 15:
            MaxHumi = 70
        elif SENSOR_TEMP_LIST[-1] < 19:
            MaxHumi = 70 + ((60 - 70) / (19 - 15)) * (SENSOR_TEMP_LIST[-1] - 15)
        elif SENSOR_TEMP_LIST[-1] < 22:
            MaxHumi = 60 + ((50 - 60) / (22 - 19)) * (SENSOR_TEMP_LIST[-1] - 19)
        elif SENSOR_TEMP_LIST[-1] < 24:
            MaxHumi = 50 + ((40 - 50) / (24 - 22)) * (SENSOR_TEMP_LIST[-1] - 22)
        else:
            MaxHumi = 40
        # 30분동안은 사용자 컨트롤 무조건 유지
        if SUDO_CONTROL_TICK_COUNT < 3:
            SUDO_CONTROL_TICK_COUNT += 1
        else:
            # 미세먼지 수치가 80보다 낮다.
            if SENSOR_AIRP_LIST[-1] < 80:
                # 현제습도가 온습도 기준 최저점보다 낮다.
                # 가습기 On, 공기청정기 Off
                # case 1
                if SENSOR_HUMI_LIST[-1] < MinHumi:
                    DEVICE_STATUS[0] = "PENDING"
                    DEVICE_STATUS[1] = "PENDING"
                    while DEVICE_STATUS != [True, False]:
                        print("CASE1", DEVICE_STATUS)
                        json_object = {"OnOff" : "On"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/HUMI", json_string, 2)
                        json_object = {"OnOff" : "Off"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/AIR", json_string, 2)
                        time.sleep(5)
                    l1 = "==============================\n"
                    l2 = GetYMDhms("t")+"\n"
                    l3 = " 습도 건조, 미세먼지 양호\n"
                    l4 = " 가습기를 On, 공기청정기 Off\n"
                    l5 = " 상태로 전환하였습니다.\n"
                    disp_text = l1 + l2 + l3 + l4 + l5
                    if ALARM_STATUS == True:
                        TELEGRAM_BOT.edit_message_text(
                            text = disp_text,
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[2])
                        homescreen = HomeScreen()
                        TELEGRAM_BOT.edit_message_text(
                            reply_markup= homescreen[0],
                            text = homescreen[1],
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[3])
                # 현제습도가 온습도 기준 최저점보다 높다.
                # 가습기 Off, 공기청정기 Off
                # case 2
                elif MaxHumi < SENSOR_HUMI_LIST[-1]:
                    DEVICE_STATUS[0] = "PENDING"
                    DEVICE_STATUS[1] = "PENDING"
                    while DEVICE_STATUS != [False, False]:
                        print("CASE2", DEVICE_STATUS)
                        json_object = {"OnOff" : "Off"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/HUMI", json_string, 2)
                        json_object = {"OnOff" : "Off"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/AIR", json_string, 2)
                        time.sleep(5)
                    l1 = "==============================\n"
                    l2 = GetYMDhms("t")+"\n"
                    l3 = " 습도 습함, 미세먼지 양호\n"
                    l4 = " 가습기를 Off, 공기청정기 Off\n"
                    l5 = " 상태로 전환하였습니다.\n"
                    disp_text = l1 + l2 + l3 + l4 + l5
                    if ALARM_STATUS == True:
                        TELEGRAM_BOT.edit_message_text(
                            text = disp_text,
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[2])
                        homescreen = HomeScreen()
                        TELEGRAM_BOT.edit_message_text(
                            reply_markup= homescreen[0],
                            text = homescreen[1],
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[3])
            # 미세먼지 수치가 80보다 높다.
            else:
                # 가습기 꺼진지 30분이 지났다면
                # 가습기 Off, 공기청정기 On
                # case 3
                if 3 < HUMI_OFF_TICK_COUNT:
                    DEVICE_STATUS[0] = "PENDING"
                    DEVICE_STATUS[1] = "PENDING"
                    while DEVICE_STATUS != [False, True]:
                        print("CASE3", DEVICE_STATUS)
                        json_object = {"OnOff" : "Off"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/HUMI", json_string, 2)
                        json_object = {"OnOff" : "On"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/AIR", json_string, 2)
                        time.sleep(5)
                    l1 = "==============================\n"
                    l2 = GetYMDhms("t")+"\n"
                    l3 = " 미세먼지 나쁨\n"
                    l4 = " 가습기를 Off, 공기청정기 On\n"
                    l5 = " 상태로 전환하였습니다.\n"
                    disp_text = l1 + l2 + l3 + l4 + l5
                    if ALARM_STATUS == True:
                        TELEGRAM_BOT.edit_message_text(
                            text = disp_text,
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[2])
                        homescreen = HomeScreen()
                        TELEGRAM_BOT.edit_message_text(
                            reply_markup= homescreen[0],
                            text = homescreen[1],
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[3])
                # 가습기가 꺼진지 30분이 안지났다면
                # 가습기 Off, 공기청정기 Off
                # case 4
                else:
                    DEVICE_STATUS[0] = "PENDING"
                    DEVICE_STATUS[1] = "PENDING"
                    while DEVICE_STATUS != [False, False]:
                        print("CASE4", DEVICE_STATUS)
                        json_object = {"OnOff" : "Off"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/HUMI", json_string, 2)
                        json_object = {"OnOff" : "Off"}
                        json_string = json.dumps(json_object)
                        MQTT_CLIENT.publish("GOLDILOCKS/CONTROL/AIR", json_string, 2)
                        time.sleep(5)
                    l1 = "==============================\n"
                    l2 = GetYMDhms("t")+"\n"
                    l3 = " 미세먼지 나쁨\n"
                    l4 = " 공기청정기를 켜기위해\n"
                    l5 = " 가습기를 미리 끕니다.\n"
                    l5 = " 가습기를 Off, 공기청정기 Off\n"
                    l6 = " 상태로 전환하였습니다.\n"
                    disp_text = l1 + l2 + l3 + l4 + l5 + l6
                    if ALARM_STATUS == True:
                        TELEGRAM_BOT.edit_message_text(
                            text = disp_text,
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[2])
                        homescreen = HomeScreen()
                        TELEGRAM_BOT.edit_message_text(
                            reply_markup= homescreen[0],
                            text = homescreen[1],
                            chat_id=OPEN_CHAT_ID[0],
                            message_id=OPEN_CHAT_ID[3])

        print("=======================================")
        MESSAGE_LOCK.release()
        tm = localtime()
        time.sleep(70 - tm.tm_sec)

if __name__ == "__main__":
    # Get Control from User, Send Device Info
    telegram_thread = threading.Thread(target=StartTelegram)
    telegram_thread.daemon = True
    telegram_thread.start()
    time.sleep(3) # turn on telegram
    print("TELEGRAM THREAD ON")
    # Get Sensor Value, Send Control
    MQTT_Thread = threading.Thread(target=StartMQTT)
    MQTT_Thread.daemon = True
    MQTT_Thread.start()
    time.sleep(3) # turn on MQTT
    print("MQTT THREAD ON")
    # Save API value to list 10min
    WAPI_Thread = threading.Thread(target=Save_API)
    WAPI_Thread.daemon = True
    WAPI_Thread.start()
    time.sleep(3) # turn on API
    print("WAPI THREAD ON")
    # Save Sensor value to list 10min
    Sensor_Thread = threading.Thread(target=Save_Sensor)
    Sensor_Thread.daemon = True
    Sensor_Thread.start()
    time.sleep(3) # turn on sensor
    print("SENSOR THREAD ON")
    # Auto Device Controler init
    Device_Control_Thread = threading.Thread(target=Auto_Device_Control)
    Device_Control_Thread.daemon = True
    Device_Control_Thread.start()
    time.sleep(3) # turn on auto control
    print("AUTO CONTROLER ON")

    fig = plt.figure()

    while True:
        T = [i for i in range(72)]
        # https://namu.wiki/w/불쾌지수
        plt.plot(
            T,
            [SENSOR_TEMP_LIST[idx] - 0.55 * (1 - 0.01 * SENSOR_HUMI_LIST[idx]) * (SENSOR_TEMP_LIST[idx] - 14.5) for idx in T], 
            c="b",
            label="in door")
        plt.plot(
            T,
            [API_TEMP_LIST[idx] - 0.55 * (1 - 0.01 * API_HUMI_LIST[idx]) * (API_TEMP_LIST[idx] - 14.5) for idx in T], 
            c="r",
            linestyle=":",
            label="out door")
        plt.legend(loc=2)
        plt.xlabel("mins")
        plt.ylabel("discomfort index")
        plt.savefig("/home/pi/Desktop/Goldilocks/justRight.png")
        plt.draw()

        tm = localtime()
        #plt.pause(80 - tm.tm_sec)
        plt.pause(2)
        fig.clear()
