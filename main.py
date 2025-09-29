# main.py — автоустановка зависимостей + запуск бота
import os, sys, subprocess

print(">> Main bootstrap starting...")

# На Python 3.13 aiohttp может пытаться собирать C-расширения и падать.
# Эта переменная включает чисто-питоновскую сборку (медленнее, но работает).
os.environ.setdefault("AIOHTTP_NO_EXTENSIONS", "1")

def run(cmd):
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd)

# Обновим pip/wheel/setuptools, затем поставим зависимости из requirements.txt
run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"])

print(">> Deps installed. Launching bot.py ...")
# Запускаем твоего бота отдельным процессом
os.execv(sys.executable, [sys.executable, "bot.py"])
