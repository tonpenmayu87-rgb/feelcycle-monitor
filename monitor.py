import requests, json, os, smtplib, sys, urllib.parse
from email.mime.text import MIMEText
from datetime import datetime, date

cfg = {
    'email':     os.environ['FEELCYCLE_EMAIL'],
    'password':  os.environ['FEELCYCLE_PASSWORD'],
    'gmail_from':os.environ['GMAIL_FROM'],
    'gmail_pass':os.environ['GMAIL_APP_PASSWORD'],
    'notify':    os.environ['NOTIFY_EMAIL'],
    'store_id':  18,
    'until_hour':12,
}

HOLIDAYS = {
    "20260101","20260112","20260211","20260223","20260320",
    "20260429","20260503","20260504","20260505","20260720",
    "20260811","20260921","20260923","20261012","20261103","20261123",
    "20270101","20270111","20270211","20270223","20270321",
    "20270429","20270503","20270504","20270505","20270719",
    "20270811","20270920","20270923","20271011","20271103","20271123",
}

def is_target(d):
    dt = datetime.strptime(d, "%Y%m%d")
    return dt.weekday() >= 5 or d in HOLIDAYS

def is_morning(t):
    return int(t.split(':')[0]) < cfg['until_hour']

def fmt_date(d):
    dt = datetime.strptime(d, "%Y%m%d")
    return f"{dt.month}/{dt.day}({'月火水木金土日'[dt.weekday()]})"

def send_mail(lessons):
    lines = ["【FEELCYCLE上野】午前クラスの空きが出ました！", ""]
    for l in lessons:
        lines.append(f"{fmt_date(l['date'])}  {l['start']}-{l['end']}  {l['name']}  残り{l['count']}人")
    lines += ["", "予約はこちら: https://m.feelcycle.com/reserve"]
    msg = MIMEText("\n".join(lines), 'plain', 'utf-8')
    msg['Subject'] = "【FEELCYCLE上野】空きあり！今すぐ予約を"
    msg['From'] = cfg['gmail_from']
    msg['To'] = cfg['notify']
    with smtplib.SMTP('smtp.gmail.com', 587) as s:
        s.starttls()
        s.login(cfg['gmail_from'], cfg['gmail_pass'])
        s.send_message(msg)
    print("メール送信完了")

# ログイン
print("ログイン中...")
sess = requests.Session()
sess.headers['User-Agent'] = 'Mozilla/5.0'
try:
    sess.get('https://m.feelcycle.com/sanctum/csrf-cookie')
except:
    pass

xsrf = urllib.parse.unquote(sess.cookies.get('XSRF-TOKEN', ''))
hdrs = {'Content-Type':'application/json','Accept':'application/json',
        'X-Requested-With':'XMLHttpRequest'}
if xsrf:
    hdrs['X-XSRF-TOKEN'] = xsrf

r = sess.post('https://m.feelcycle.com/api/user/login',
              json={'email': cfg['email'], 'password': cfg['password']}, headers=hdrs)
if r.status_code >= 400:
    print(f"ERROR: ログイン失敗 status={r.status_code}"); sys.exit(1)
print("ログイン成功")

xsrf = urllib.parse.unquote(sess.cookies.get('XSRF-TOKEN', xsrf))
cal_hdrs = {'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}
if xsrf:
    cal_hdrs['X-XSRF-TOKEN'] = xsrf

# スケジュール取得
today = date.today().strftime('%Y-%m-%d')
url = (f"https://m.feelcycle.com/api/reserve/lesson_calendar"
       f"?mode=2&shujiku_type=1&get_direction=1"
       f"&get_starting_date={today}&search_store[]={cfg['store_id']}")
cal = sess.get(url, headers=cal_hdrs).json()
if cal.get('result_code') != 0:
    print(f"ERROR: API result_code={cal.get('result_code')}"); sys.exit(1)
print("スケジュール取得完了")

# 状態読み込み
STATE = 'state.json'
is_first = not os.path.exists(STATE) or os.path.getsize(STATE) == 0
prev = json.load(open(STATE)) if not is_first else {}

# 空き確認
new_avail, new_state = [], {}
for day in cal.get('lesson_list', []):
    d = day.get('lesson_date', '')
    if not is_target(d): continue
    for les in day.get('schedule', []):
        if not is_morning(les.get('lesson_start', '99:00')): continue
        key = f"{d}_{les['lesson_start']}_{''.join(c for c in les['lesson_name'] if c.isalnum())}"
        cnt = int(les.get('reserve_status_count', 0))
        new_state[key] = cnt
        if not is_first:
            p = prev.get(key)
            if cnt > 0 and (p is None or p == 0):
                new_avail.append({'date':d,'start':les['lesson_start'],
                                  'end':les['lesson_end'],'name':les['lesson_name'],'count':cnt})

if new_avail:
    print(f"空き検出: {len(new_avail)}件")
    send_mail(new_avail)
elif is_first:
    print("初回起動: 現在の状態を保存しました")
else:
    print("変化なし（空きなし）")

json.dump(new_state, open(STATE, 'w'), ensure_ascii=False)
