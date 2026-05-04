import json

FILE = "economy.json"

def load():
    try:
        return json.load(open(FILE))
    except:
        return {}

def save(data):
    json.dump(data, open(FILE, "w"))

data = load()

def get_balance(user):
    return data.get(str(user), 0)

def add_money(user, amount):
    uid = str(user)
    data[uid] = data.get(uid, 0) + amount
    save(data)
