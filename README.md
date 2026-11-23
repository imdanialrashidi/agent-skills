# نصب Agent Skills روی لینوکس

این نصب‌کننده ۱۱ Skill فهرست `skills.txt` را برای تمام پروژه‌های حساب فعلی لینوکس در دسترس قرار می‌دهد.

## اجرا

برای اولین نصب به Python 3.9 یا جدیدتر، Git و دسترسی به GitHub نیاز داری. با حساب کاربری خودت اجرا کن.

```sh
python3 install.py --dry-run
python3 install.py
```

دستور اول فهرست منابع و مسیرهای نصب را بدون دانلود نشان می‌دهد. بعد از نصب، در Agent یک نشست جدید باز کن.

## اضافه کردن Skill

برای هر Skill یک خط به `skills.txt` اضافه کن. چهار ستون به‌ترتیب نام داخل `SKILL.md`، مخزن GitHub، مسیر پوشهٔ Skill در مخزن و در صورت نیاز شناسهٔ commit یا نام branch/tag هستند.

```text
# NAME OWNER/REPO DIRECTORY [GIT_REF]
my-skill your-org/your-repo skills/my-skill
```

برای Skill واقع در ریشهٔ یک مخزن، به جای مسیر از `.` استفاده کن. برای بازتولیدپذیری، تمام منابع اولیه با شناسهٔ کامل commit ثبت شده‌اند. اگر ستون آخر را خالی بگذاری، اسکریپت شاخهٔ پیش‌فرض مخزن را دنبال می‌کند. برای اعمال تغییرات فهرست، همان `python3 install.py` را دوباره اجرا کن. با `--manifest my-skills.txt` می‌توانی فهرست دیگری بدهی.

## مسیرهای کشف

نسخه‌های دانلودشده در `${XDG_DATA_HOME:-~/.local/share}/agent-skills/versions/` قرار می‌گیرند. مسیر مشترک کشف Skillها `~/.agents/skills/` است. نصب‌کننده به همین مجموعه از مسیرهای سازگار با Codex، Claude Code، Cursor، Gemini CLI، GitHub Copilot، OpenCode و Windsurf لینک می‌دهد و Skillهای هم‌نامی را که از قبل دستی نصب شده‌اند حفظ می‌کند.

اگر Agent دیگری مسیر خاص خودش را دارد، آن را با `--target` بده. این گزینه برای ثبت چند مسیر قابل‌تکرار است.

```sh
python3 install.py --target "$HOME/.your-agent/skills"
```

دسترسی و نحوهٔ اجرای Skill به نسخه و تنظیمات هر Agent بستگی دارد. این نصب برای Agentهایی است که Skillها را از فایل‌سیستم محلی می‌خوانند. [مسیرهای Codex](https://developers.openai.com/codex/skills) · [مسیرهای Agentهای دیگر](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)
