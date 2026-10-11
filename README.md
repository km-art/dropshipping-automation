# Automation & Cloud API — دليل التشغيل

سكربتين شغالين فعلاً، مبنيين على مواصفات ملف الخطة الأصلي:

| الملف | وظيفته |
|---|---|
| `order_sync.py` | سيرفر Flask بيستقبل Webhook لما يتعمل أوردر جديد في المتجر، وبيحوّله أوتوماتيك لسبلاير CJ Dropshipping عن طريق الـ API. |
| `inventory_sync.py` | بيقرأ شيت "Product Research & Niche" من ملف الإكسل بتاعك، ويحدّث الأسعار على شوبيفاي تلقائياً، وكمان يحدّث `products_map.json` اللي بيستخدمه `order_sync.py`. |
| `products_map.json` | خريطة SKU → اسم المنتج / السعر / السبلاير — مولّدة من نفس بيانات الإكسل. |

## 1) التركيب المحلي (تجربة على جهازك)

```bash
cd automation
python -m venv venv
source venv/bin/activate      # على ويندوز: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # واملى القيم الحقيقية
```

## 2) شغّل مزامنة الأسعار

```bash
python inventory_sync.py ../Dropshipping_Cloud_Automation_Masterplan.xlsx
```

لو `SHOPIFY_STORE_URL` و `SHOPIFY_ACCESS_TOKEN` مش متظبطين في `.env`، السكربت هيحدّث بس `products_map.json` محلياً من غير ما يلمس المتجر — مفيد للتجربة الأول.

## 3) شغّل سيرفر استقبال الطلبات

```bash
python order_sync.py
```

هيشتغل على `http://localhost:5000`. جرّبه بـ:

```bash
curl http://localhost:5000/health
```

## 4) اربطه بشوبيفاي (Webhook)

في لوحة تحكم شوبيفاي: **Settings → Notifications → Webhooks → Create webhook**
- Event: `Order creation`
- Format: `JSON`
- URL: `https://<الدومين-بتاعك>/webhook/order`

خد الـ **Webhook signing secret** اللي شوبيفاي بيديهولك وحطه في `SHOPIFY_WEBHOOK_SECRET` — ده بيمنع أي حد يبعتلك أوردرات وهمية.

## 5) الرفع على السحابة (Deployment)

أي سيرفر Python بسيط يكفي — مقترحات مجانية/رخيصة:
- **Render.com**: اعمل "Web Service" جديد، اربطه بالريبو، `gunicorn order_sync:app` كأمر تشغيل.
- **Railway.app**: نفس الفكرة، دعم مباشر لـ Flask.
- **PythonAnywhere**: مناسب لو عايز حل بسيط بدون Docker.

بعد الرفع، بدّل الـ URL في Webhook إعدادات شوبيفاي بالدومين النهائي.

## 6) تشغيل مزامنة الأسعار بشكل دوري

لو عايز `inventory_sync.py` يشتغل لوحده كل يوم (مش يدوي)، ضيفه كـ **Scheduled Task** على نفس منصة الاستضافة (Render/Railway عندهم Cron Jobs جاهزة)، أو استخدم `cron` لو عندك VPS:

```
0 6 * * * /path/to/venv/bin/python /path/to/inventory_sync.py /path/to/masterplan.xlsx
```

## ملاحظات مهمة قبل التشغيل الفعلي

1. **مفاتيح API حقيقية**: السكربت جاهز بس محتاج مفاتيح CJ Dropshipping وشوبيفاي الحقيقية بتاعتك — مش موجودة في الملف الأصلي.
2. **الـ SKUs لازم تتطابق**: لازم تحط نفس الـ SKU (PROD-001... إلخ) في شوبيفاي عشان الربط يشتغل صح.
3. **جرّب على متجر تجريبي (Development Store) الأول** قبل ما تفعّله على المتجر الحقيقي.
