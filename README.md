# نظام إدارة الصيانة الدورية للمصانع

نظام Django كامل لإدارة دورة فحص يومية مستقلة لكل مصنع، بواجهة عربية RTL وREST API لتطبيق Android يعمل بأسلوب Offline First.

## المكونات

- Django 5.2 وDjango REST Framework.
- SQLite حاليًا، مع Queries وModels قابلة للنقل إلى PostgreSQL.
- JWT Access/Refresh، وصلاحيات حسب الدور والمصنع.
- Dashboard عربية مخصصة ومتجاوبة للكمبيوتر والتابلت.
- OpenAPI وSwagger.
- Service Layer في `maintenance/services/cycle.py`؛ لا يتكرر منطق الدورة بين الواجهة والـAPI.

الـmigration المرجعية تنشئ فقط **مصنع 1، مصنع 2، مصنع 3، وقائمتي الفحص المذكورتين في المتطلبات**. لا ينشئ المشروع ماكينات أو مستخدمين أو تقارير أو إحصاءات تجريبية.

## التثبيت والتشغيل

يتطلب Python 3.11 أو أحدث.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

في Linux/macOS استخدم `source .venv/bin/activate` و`cp .env.example .env`.

بعد إنشاء الـsuperuser افتح:

- Dashboard: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/api/docs/`
- OpenAPI Schema: `http://127.0.0.1:8000/api/schema/`
- Django Admin التقني: `http://127.0.0.1:8000/admin/`

## متغيرات البيئة

انسخ `.env.example` إلى `.env` واضبط القيم في بيئة التشغيل. يقرأ المشروع الملف محليًا، ويمكن في الإنتاج حقن القيم مباشرة من systemd أو Docker أو مدير الأسرار.

- `SECRET_KEY`: مفتاح طويل وسري، إلزامي في الإنتاج.
- `DEBUG`: يجب أن يكون `False` في الإنتاج.
- `ALLOWED_HOSTS`: قائمة النطاقات مفصولة بفاصلة.
- `CORS_ALLOWED_ORIGINS`: Origins المسموح بها فقط، بدون `*`.
- `CSRF_TRUSTED_ORIGINS`: عناوين HTTPS الموثوقة للـDashboard.
- `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`: أعمار التوكن.
- `LOGIN_THROTTLE`: حد طلبات الدخول، افتراضيًا `10/minute`.
- `SECURE_SSL_REDIRECT`: اجعله `True` عندما تنتهي TLS عند التطبيق مباشرة.

لا تضع `.env` أو كلمات المرور أو Tokens في Git.

## دورة الصيانة

- لكل مصنع حالة دورة مستقلة ومقفلة داخل Transaction عند التسجيل.
- مصنع 1 و3: المكن العادي ثم المكابس ثم العودة لأول ماكينة عادية.
- مصنع 2: المكن العادي ثم مكن السوستة ثم العودة لأول ماكينة عادية.
- العنصر لا يتقدم بسبب مرور اليوم؛ يتقدم فقط في أول يوم تالٍ لتقرير مكتمل.
- إذا تغيّر الترتيب يبقى العنصر الحالي ما دام نشطًا، ويُطبق الترتيب على ما بعده.
- الأرشفة Soft Delete وتحافظ على جميع التقارير التاريخية.
- التقارير السابقة لليوم الحالي مقفلة، وفق `Africa/Cairo`.

## ربط تطبيق Android

كل المسارات تحت `/api/v1/`، باستثناء صفحات التوثيق:

```text
POST /api/v1/auth/login/
POST /api/v1/auth/refresh/
GET  /api/v1/auth/me/
GET  /api/v1/mobile/bootstrap/
GET  /api/v1/mobile/current-maintenance/
POST /api/v1/mobile/reports/
PUT  /api/v1/mobile/reports/{id}/
POST /api/v1/mobile/sync/reports/
```

الدخول يرسل `phone` و`password`. أرسل Access Token في:

```text
Authorization: Bearer <access-token>
```

ينبغي استدعاء `mobile/bootstrap/` بعد الدخول وتخزين ناتجه محليًا؛ فهو يعيد المستخدم والمصنع والأصول النشطة وترتيبها وإصدار الترتيب وقوالب الفحص وعنصر اليوم وتقرير اليوم.

كل تقرير ينشئ له الهاتف UUID في `client_report_id`. إعادة نفس التقرير لا تنشئ سجلًا مكررًا. لتحديث تقرير اليوم استخدم `last_modified_at_device` أحدث. المزامنة الدفعية يجب أن ترسل التقارير مرتبة حسب `report_date` ثم `completed_at_device`، وتعيد نتيجة مستقلة لكل عنصر: `synced` أو `already_synced` أو `rejected` أو `conflict`.

لا يرسل التطبيق `factory_id` كمصدر ثقة؛ الخادم يستنتج المصنع من حساب المشرف ويتحقق من الأصل وقائمة الفحص وتسلسل الدورة.

## الاختبارات والفحص

```powershell
python manage.py check
python manage.py test
python manage.py spectacular --file schema.yml --validate
```

تغطي الاختبارات دورات المصانع الثلاثة، الانتقالات والالتفاف، عدم التقدم دون تقرير، منع تكرار اليوم، القفل، Offline delayed sync، idempotency، إعادة الترتيب، الأرشفة، قيود الأنواع، وعزل صلاحيات المصانع.

## الانتقال إلى PostgreSQL

ثبّت برنامج التشغيل أولًا:

```powershell
python -m pip install "psycopg[binary]"
```

ثم اضبط:

```text
DB_ENGINE=django.db.backends.postgresql
DB_NAME=maintenance
DB_USER=maintenance_user
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
```

أنشئ قاعدة فارغة، شغّل `python manage.py migrate`، ثم انقل البيانات بأداة ترحيل مناسبة ومختبرة. لا تستخدم أي SQL خاص بـSQLite داخل التطبيق.

## ملاحظات الإنتاج

- استخدم خادم WSGI/ASGI مثل Gunicorn أو Uvicorn خلف HTTPS reverse proxy.
- شغّل `python manage.py collectstatic` وقدّم الملفات الثابتة من Nginx أو خدمة ملفات ثابتة.
- أنشئ نسخًا احتياطية دورية، وفعّل مراقبة Logs، واضبط CORS وHosts على القيم الفعلية فقط.
- SQLite مناسبة للمرحلة الحالية، أما تعدد الكتابات في الإنتاج فيُفضّل له PostgreSQL.
