# Лицензийн үүргийн өдөр тутмын хяналт → Google Chat

Obligation Register spreadsheet-ээс өдөр бүр автоматаар Google Chat space руу
удирдлагад ойлгомжтой товч мэдээ болон exception анхааруулга илгээнэ.

Эх дата: `1cP-i5klZviD4PCRPSN-mwil-P1fmv_07ey10IKZArRk` — өөр эх сурвалж ашиглахгүй.

**Хуудас оноор автоматаар сонгогдоно.** 2026 онд `OB 2026`, 2027 он гармагц
`OB 2027`, 2028 онд `OB 2028` … гэх мэт. Код өөрчлөх шаардлагагүй.
Шинэ оны хуудас хараахан үүсээгүй бол хамгийн сүүлийн оныг түр ашиглаад,
Chat карт дээр **⚠️ анхааруулга** харуулна — чимээгүй хоосон тайлан гарахаас
сэргийлнэ.

---

## Юу илгээгддэг вэ

### 1. Өдөр тутмын товч (`daily`)

Гурван хэсэг:

- **ӨНӨӨДРИЙН ДҮГНЭЛТ** — нэг мөр: 🔴 хугацаа хэтэрсэн / 🔴 асуудалтай төлөв
  (Exception open · Rejected) / 🟠 7 хоногт дуусах / 🟢 хэвийн
- **🔴 АСУУДАЛТАЙ N ҮҮРЭГ** — дүгнэлтэд дурдсан үүрэг бүрийг нэрлэнэ:
  шалтгаан (хэтэрсэн хоног эсхүл төлөв), Obligation ID, нэр, Tier, лиценз,
  эзэн. Ингэснээр "3 үүрэг асуудалтай" гэсэн тоо аль үүрэг болох нь
  тодорхойгүй үлдэхгүй. Хэтэрсэн нь эхэнд, дараа нь `Exception open` /
  `Rejected` төлөвтэй нь. Асуудалгүй үед энэ хэсэг гарахгүй.
- **ХАМГИЙН ОЙРТСОН 5 ҮҮРЭГ** — үлдсэн хоног, Obligation ID, үүргийн нэр,
  Tier, лиценз, эзэн. Дээр нэрлэгдсэн үүргийг давхардуулж жагсаахгүй.

Асуудалтай үүргийн жагсаалт `MAX_EXCEPTION_ITEMS` (анхдагч 10)-аар
хязгаарлагдана; илүү гарвал "…бусад N үүрэг" гэж тэмдэглэнэ.

Доор нь бүртгэл рүү очих товч. Толгойд огноо, идэвхтэй үүргийн тоо болон
уншсан хуудас харагдана.

### 2. Exception анхааруулга (`exceptions`)

Зөвхөн **шинээр илэрсэн** тохиолдлыг илгээнэ — нэг асуудал давтагдахгүй.
Мөр бүрээс хамгийн ноцтой нэг шалтгааныг л сонгоно.

| Түвшин | Нөхцөл |
|---|---|
| 🔴 КРИТИК | Хугацаа хэтэрсэн |
| 🔴 КРИТИК | Төлөв: Overdue / Rejected / Exception open |
| 🔴 КРИТИК | Tier 1 үүрэг 7 хоногийн дотор дуусах |
| 🟠 АНХААР | 30 хоногт дуусах ба нотлох баримт Missing/Partial |
| 🟠 АНХААР | 7 хоногт дуусах ба ажил эхлээгүй |
| 🟡 БАРИМТ | 30 хоногт дуусах ба Drive холбоосгүй |

### 3. Тайлангийн хяналт (`watchdog`)

Go-live-ийн "100% тогтмол" шаардлагыг хамгаална:

- 7 хоногийн тайлан 8 хоногоос удаан гараагүй бол
- Run log-д `SENT` биш төлөвт гацсан ажиллуулалт байвал

---

## Суулгах

### 1. Багцууд

```powershell
cd c:\Users\margad.p\Desktop\FIRST_CHATBOT
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Google хандалт тохируулах

Скрипт хүн биш, **service account**-аар spreadsheet уншина. Ингэснээр
хэн нэгний нэвтрэлтээс хамаарахгүй, серверт ч ажиллана.

1. [console.cloud.google.com](https://console.cloud.google.com) → project сонгох (эсхүл шинээр үүсгэх)
2. **APIs & Services → Library** → `Google Sheets API` → **Enable**
3. **APIs & Services → Credentials → Create credentials → Service account**
   - Нэр: `obligation-monitor` · Role шаардлагагүй → **Done**
4. Үүссэн service account дээр дарж → **Keys → Add key → Create new key → JSON**
   - Татагдсан файлыг `service-account.json` нэрээр төслийн үндэс хавтсанд хийнэ
5. JSON доторх `client_email` утгыг хуулна
   (ж: `obligation-monitor@төсөл.iam.gserviceaccount.com`)
6. **Spreadsheet-ээ нээж → Share → тэр имэйлийг Viewer эрхээр нэмнэ**

> 6-р алхмыг мартвал `403 The caller does not have permission` гарна.

### 3. `.env` бэлдэх

`.env` файлд Google Chat webhook URL байх ёстой. Одоо байгаа файл
нүцгэн URL агуулж байгаа бөгөөд **тэр хэвээрээ ажиллана**. Тодорхой болгох
бол `.env.example`-ийг үлгэр болгож дараах хэлбэрт оруулж болно:

```
CHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/.../messages?key=...&token=...
SPREADSHEET_ID=1cP-i5klZviD4PCRPSN-mwil-P1fmv_07ey10IKZArRk
GOOGLE_APPLICATION_CREDENTIALS=service-account.json
```

### 4. Шалгах

```powershell
python -m obligation_monitor sheets      # хуудсуудын жинхэнэ нэрийг харах
python -m obligation_monitor test        # уншилт + Chat холболт шалгах
python -m obligation_monitor daily --dry-run   # илгээхгүйгээр картыг харах
```

`sheets` командын гаралтад `OB 2026`, `OB 2027` хуудас олдоогүй бол
жинхэнэ нэрийг нь `.env`-д бичнэ:

```
REGISTER_SHEETS=Жинхэнэ нэр 1,Жинхэнэ нэр 2
```

### 5. Хуваарь суулгах (Windows Task Scheduler)

```powershell
# Өдөр бүр 10:00 — ерөнхий товч
schtasks /create /f /tn "Obligation daily" /tr "C:\Users\margad.p\Desktop\FIRST_CHATBOT\run.bat daily" /sc daily /st 10:00

# 10:00, 14:00, 18:00 — exception хяналт (ажлын цагт л)
schtasks /create /f /tn "Obligation exceptions" /tr "C:\Users\margad.p\Desktop\FIRST_CHATBOT\run.bat exceptions" /sc daily /st 10:00 /ri 240 /du 09:00

# Даваа 10:30 — тайлангийн хяналт
schtasks /create /f /tn "Obligation watchdog" /tr "C:\Users\margad.p\Desktop\FIRST_CHATBOT\run.bat watchdog" /sc weekly /d MON /st 10:30
```

`/ri 240 /du 09:00` = 10:00-аас эхлэн 9 цагийн турш 240 минут тутам давтана,
өөрөөр хэлбэл 10:00 · 14:00 · 18:00. Шөнө мэдэгдэл ирэхгүй.

`run.bat` нь гаралтыг `run.log`-д бичнэ.

> **Анхаар:** Task Scheduler зөвхөн компьютер асаалттай үед ажиллана.
> Амралтын өдөр эсхүл унтраалттай үед мэдэгдэл алгасна. Тасралтгүй
> ажиллуулах бол cloud VM, GitHub Actions (cron) эсхүл Cloud Run Job руу
> зөөнө — код өөрчлөх шаардлагагүй, зөвхөн `.env` + `service-account.json`
> хоёрыг secret болгож өгнө.

---

## Командууд

| Команд | Юу хийх |
|---|---|
| `daily` | Өдөр тутмын товч — үргэлж илгээнэ |
| `exceptions` | Зөвхөн шинэ exception илгээнэ |
| `watchdog` | 7 хоногийн тайлан гарсан эсэхийг шалгана |
| `test` | Уншилт болон Chat холболт шалгана |
| `sheets` | Spreadsheet-ийн хуудсуудыг жагсаана |

Нэмэлт flag:

| Flag | Утга |
|---|---|
| `--dry-run` | Илгээхгүй, JSON-г консолд хэвлэнэ |
| `--all` | `exceptions`: шинэ эсэхийг үл харгалзан бүгдийг илгээнэ |
| `--env ЗАМ` | Өөр `.env` файл ашиглана |

---

## Тохируулж болох утгууд

`.env` дотор:

| Түлхүүр | Анхдагч | Тайлбар |
|---|---|---|
| `CRITICAL_DAYS` | 7 | "Нэн яаралтай" гэж үзэх хоног |
| `DUE_SOON_DAYS` | 30 | "Ойртсон" гэж үзэх хоног |
| `MAX_LIST_ITEMS` | 5 | Картад жагсаах мөрийн тоо |
| `REGISTER_SHEET_PATTERN` | `OB {year}` | Оны хуудасны нэрийн загвар |
| `REGISTER_SHEETS` | *(хоосон)* | Оны автомат сонголтыг үл тоомсорлож тодорхой хуудас тогтооно |
| `RUNLOG_SHEET_HINT` | `weekly` | Run log хуудасны нэрийн хэсэг |
| `TIME_ZONE` | `Asia/Ulaanbaatar` | Цагийн бүс |
| `STATE_PATH` | `state.json` | Өмнөх ажиллуулалтын төлөв |

---

## Бүтэц

```
obligation_monitor/
  config.py     — .env уншилт, тохиргоо
  sheets.py     — Sheets API, багана тайлах, огноо задлах
  analyze.py    — нэгтгэл, exception илрүүлэлт, run log шалгалт
  cards.py      — Google Chat cardsV2 бүтээх
  chat.py       — webhook руу илгээх
  state.py      — өчигдрийн тоо, мэдэгдсэн exception хадгалах
  __main__.py   — CLI
```

---

## Техникийн тэмдэглэл

- **Багануудыг гарчгийн нэрээр олдог** (`Obligation ID`, `Дараагийн due date`, …).
  Register 57 баганатай, дунд нь хоосон болон helper багана олон тул индексээр
  хандвал эмзэг. Гарчиг өөрчлөгдвөл [`sheets.py`](obligation_monitor/sheets.py)
  доторх `_COLUMNS` толийд шинэ нэрийг нэмнэ.
- **Зөвхөн тухайн оны хуудсыг уншина.** Статус, evidence, Drive link баганыг
  оноор нь (`2026 Одоогийн статус` г.м.) эхэлж хайж, олдохгүй бол
  `Active … (helper)` багана руу шилжинэ.
- Нэг ID давтагдвал **идэвхтэй мөчлөгтэй** (due date-тай) мөрийг сонгоно.
- `Not applicable` эсхүл хоосон статустай мөрийг тооцоололд оруулахгүй.
- Огноог `Date`, `yyyy-mm-dd` текст болон Sheets-ийн серийн дугаар
  (ж: `46324`) гурван хэлбэрээр таньдаг. `m/d/yyyy` хэлбэрийг АНУ-ын
  дарааллаар (сар/өдөр) уншина — run log дээрх `8/6/2026` ийм байсан.
- Evidence нь `Not yet due` / `Not applicable` бол Drive холбоос
  шаардахгүй — тийм мөрийг "холбоосгүй" гэж тоолохгүй.
- Өчигдрийн тоо болон мэдэгдсэн exception `state.json`-д хадгалагдана.
  Эхнээс нь эхлүүлэх бол тэр файлыг устгана.

---

## Аюулгүй байдал

`.env`, `service-account.json`, `state.json` гурвыг **git-д хэзээ ч оруулахгүй**
— [`.gitignore`](.gitignore)-д аль хэдийн нэмсэн. Webhook URL-тэй хэн ч
тухайн Chat space руу мессеж бичих боломжтой.

---

## Асуудал гарвал

| Шинж тэмдэг | Шалтгаан |
|---|---|
| `Service account файл олдсонгүй` | 2-р алхмын JSON түлхүүр байхгүй |
| `403 The caller does not have permission` | Spreadsheet-ийг service account-тай Share хийгээгүй |
| `CHAT_WEBHOOK_URL олдсонгүй` | `.env` дотор webhook URL байхгүй |
| `Chat илгээхэд алдаа (404)` | Webhook устсан эсхүл буруу хуулсан |
| `test` 0 үүрэг буцаана | Тухайн оны хуудас олдсонгүй — `sheets` командаар шалгана |
| Картад "хуудас хараахан үүсээгүй" анхааруулга | Шинэ он гарсан ч `OB <он>` хуудас үүсээгүй — бүртгэлд шинэ оны хуудсыг нэмнэ |
| Тоо dashboard-тай таарахгүй | Dashboard 575 мөрийг бүхэлд нь, энэ скрипт `Not applicable`-ийг хассан идэвхтэй мөрийг тоолно |
