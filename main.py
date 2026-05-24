from flask import Flask, request, jsonify, make_response, send_file
import requests, os, anthropic, json, re

app = Flask(__name__)

DAFTRA_BASE = 'https://maealequrtoba.daftra.com/api2'
APIKEY = os.environ.get('APIKEY', 'c4c035341dbe1da1531b227d89f6e2f481252766')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

CLIENT_ALIASES = {
    'مهجة': 'ريميندر',
    'reminder': 'ريميندر',
    'الخدمات التجارية المتكاملة': 'الخدمات التجارية المتكاملة',
    'خدمات متكاملة': 'الخدمات التجارية المتكاملة',
    'حباب': 'مؤسسة الجبر',
    'الحباب': 'مؤسسة الجبر',
    'ماهر حباب': 'مؤسسة الجبر',
    'ماهر عبدالله': 'مؤسسة الجبر',
    'الجبر': 'مؤسسة الجبر',
}

# رقم الهوية -> اسم الموظف (من التأمينات الاجتماعية)
EMPLOYEE_IDS = {
    '2229429275': 'عمرو الحلبي',          # مالك الشركة
    '2155703453': 'بلال جلال غانم',        # موظف
    '2500894296': 'MD ANIS',
    '2549846075': 'MD JAULHAS MOLLA',
    '1123351007': 'محمد المجيدل',
    '2544919612': 'TAUFEEK AHMAD',
    '2544919596': 'TAREKH HUSEN',
    '1131768192': 'فهد البطي',
    '2568475756': 'احمد محمد حماد',
    '1126192390': 'فهد العليان',
    '2602072692': 'RAMJAN MANSHUR',
    '2602072783': 'NOORUL HODA KHAN',
    '2612225173': 'AFROJ SALMANI',
    '2229429267': 'اميرة',                 # أم المالك - شخصي
    '2619122530': 'SAVEJ ABDUL RAHMAN',
    '2630277883': 'SADDAM KHAN',
    '2630277933': 'MD ARIF HOSSAIN',
    '2636857225': 'WAJID ALI',
    '1136786959': 'احمد الفضل',
    '2576905463': 'MD AMAN ULLAH',
    '2229429291': 'يزن الحلبي',            # مدير فرع القصيم
    '2551964485': 'KAMAL HOSSAIN',
    '2574846610': 'SIKANDAR GUPTA',        # مدير تركيب الرياض
}

# رقم الهوية -> تصنيف
EMPLOYEE_CATEGORY = {
    '2229429275': 'personal',    # المالك
    '2229429267': 'personal',    # أميرة - أم المالك
    '2155703453': 'salary',
    '2500894296': 'salary',
    '2549846075': 'salary',
    '1123351007': 'salary',
    '2544919612': 'salary',
    '2544919596': 'salary',
    '1131768192': 'salary',
    '2568475756': 'salary',
    '1126192390': 'salary',
    '2602072692': 'salary',
    '2602072783': 'salary',
    '2612225173': 'salary',
    '2619122530': 'salary',
    '2630277883': 'salary',
    '2630277933': 'salary',
    '2636857225': 'salary',
    '1136786959': 'salary',
    '2576905463': 'salary',
    '2229429291': 'salary',
    '2551964485': 'salary',
    '2574846610': 'salary',
}

ACCOUNT_TO_CLIENT = {
    # عملاء
    '129000010006086890598': 'ريميندر',
    '12900608016890598': 'ريميندر',
    '200000010006080174447': 'علي سعود',
    # موظفون
    '640000010006087461738': 'SALAMUDDIN',
    '077050010006087399166': 'SIKANDAR',
    '077050010006087400188': 'TAUFEEK',
    '697000010006086135855': 'يزن',
    '192000010006080456273': 'مالك',
    'MOATAZ': 'معتز',
    # نقل
    '331000010006086567547': 'عبدالحسيب',
    'AMRO_BADAWI': 'عمرو بدوي',
    # موردون
    '377000010006080000888': 'شركة السنا للرخام والسيراميك',
    '538000010006080000223': 'شركة الفرات للرخام',
    '602000010006080654780': 'شركة اسوار الخليج',
    '487000010006085245725': 'شركة هواهوي ستون',
    # إيجار
    '599000010006080888888': 'سليمان المهوس',
    # حكومي
    '282000010006086606237': 'مؤسسة قوس قزح',
    # شخصي
    '077050010006084823853': 'عمرو الحلبي',
    '539000010006085772890': 'اميرة',
}

ACCOUNT_CATEGORY = {
    '129000010006086890598': 'client_payment',
    '12900608016890598': 'client_payment',
    '200000010006080174447': 'client_payment',
    '640000010006087461738': 'salary',
    '077050010006087399166': 'salary',
    '077050010006087400188': 'salary',
    '697000010006086135855': 'salary',
    '192000010006080456273': 'salary',
    'MOATAZ': 'salary',
    '331000010006086567547': 'transportation',
    'AMRO_BADAWI': 'transportation',
    '377000010006080000888': 'local_supplier',
    '538000010006080000223': 'local_supplier',
    '602000010006080654780': 'local_supplier',
    '487000010006085245725': 'local_supplier',
    '599000010006080888888': 'rent',
    '282000010006086606237': 'government',
    '077050010006084823853': 'personal',
    '539000010006085772890': 'personal',
}

EXPENSE_ACCOUNT_ID = {
    'salary':         '56',
    'rent':           '52',
    'transportation': '52',
    'government':     '52',
    'bank_fee':       '52',
    'personal':       '54',
    'loan':           '54',
    'other':          '54',
}

EXCLUDE_KEYWORDS = ['ديزل', 'محروقات', 'diesel', 'fuel']
CLEANUP_CUTOFF = '2026-04-01'

def should_exclude(text):
    text = (text or '').lower()
    return any(kw.lower() in text for kw in EXCLUDE_KEYWORDS)

def fetch_all_pages(endpoint):
    items = []
    page = 1
    while True:
        r = requests.get(f"{DAFTRA_BASE}/{endpoint}", headers={'APIKEY': APIKEY},
                         params={'limit': 50, 'page': page}, timeout=30)
        data = r.json().get('data', [])
        if not data:
            break
        items.extend(data)
        if len(data) < 50:
            break
        page += 1
    return items

def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, APIKEY'
    return r

def get_open_invoices(invoice_type='sales'):
    try:
        all_invoices = []
        endpoint = 'invoices' if invoice_type == 'sales' else 'purchase_invoices'
        for status in ['0', '2']:
            page = 1
            while True:
                resp = requests.get(f"{DAFTRA_BASE}/{endpoint}", headers={'APIKEY': APIKEY},
                                    params={'payment_status': status, 'limit': 50, 'page': page})
                data = resp.json()
                invoices = data.get('data', [])
                if not invoices:
                    break
                all_invoices.extend(invoices)
                if len(invoices) < 50:
                    break
                page += 1
        seen = set()
        unique = []
        for inv in all_invoices:
            key = 'Invoice' if invoice_type == 'sales' else 'PurchaseInvoice'
            inv_id = inv.get(key, {}).get('id')
            if inv_id and inv_id not in seen:
                seen.add(inv_id)
                unique.append(inv)
        return unique
    except:
        return []

def normalize_name(name):
    name = (name or '').lower().strip()
    for alias, canonical in CLIENT_ALIASES.items():
        if alias in name:
            return canonical.lower()
    return name

def extract_account_from_text(text):
    text = text or ''
    m = re.search(r'(?:FRACCT|TOACCT|FROMACCT)[/\\](\d{10,})', text)
    if m:
        return m.group(1)
    m = re.search(r'CA:\s*(\d{10,})', text)
    if m:
        return m.group(1)
    return None

def extract_id_from_text(text):
    """Extract Saudi/Iqama ID number from transaction text"""
    text = text or ''
    m = re.search(r'\b([12]\d{9})\b', text)
    if m:
        return m.group(1)
    return None

def client_name_matches(party, inv_client):
    if not party or not inv_client:
        return False
    acc = extract_account_from_text(party)
    if acc and acc in ACCOUNT_TO_CLIENT:
        canonical = ACCOUNT_TO_CLIENT[acc].lower()
        return canonical in normalize_name(inv_client)
    p = normalize_name(party)
    c = normalize_name(inv_client)
    p_words = [w for w in p.split() if len(w) >= 4]
    c_words = [w for w in c.split() if len(w) >= 4]
    for pw in p_words:
        if pw in c:
            return True
    for cw in c_words:
        if cw in p:
            return True
    return False

def match_payment(amount, open_invoices, party='', description='', invoice_key='Invoice'):
    combined_text = f"{party} {description}"
    acc = extract_account_from_text(combined_text)
    if acc and acc in ACCOUNT_TO_CLIENT:
        party = ACCOUNT_TO_CLIENT[acc]

    client_field = 'client_business_name' if invoice_key == 'Invoice' else 'supplier_name'
    client_invoices = [
        inv for inv in open_invoices
        if client_name_matches(combined_text, inv.get(invoice_key, {}).get(client_field, ''))
    ]
    search_pools = [client_invoices, open_invoices] if client_invoices else [open_invoices]

    for pool in search_pools:
        matches = []
        for inv in pool:
            inv_data = inv.get(invoice_key, {})
            unpaid = float(inv_data.get('summary_unpaid', 0) or 0)
            total = float(inv_data.get('summary_total', 0) or 0)
            inv_amount = unpaid if unpaid > 0 else total
            if inv_amount <= 0:
                continue
            diff = abs(amount - inv_amount) / inv_amount
            if diff <= 0.05:
                matches.append({
                    'invoice_id': inv_data.get('id'),
                    'invoice_no': inv_data.get('no'),
                    'client': inv_data.get(client_field, ''),
                    'amount': inv_amount,
                    'confidence': 'exact' if diff < 0.01 else 'close'
                })
        if matches:
            return matches

        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                inv1 = pool[i].get(invoice_key, {})
                inv2 = pool[j].get(invoice_key, {})
                a1 = float(inv1.get('summary_unpaid', 0) or inv1.get('summary_total', 0) or 0)
                a2 = float(inv2.get('summary_unpaid', 0) or inv2.get('summary_total', 0) or 0)
                combined = a1 + a2
                if combined > 0 and abs(amount - combined) / combined <= 0.05:
                    return [{
                        'invoice_id': f"{inv1.get('id')},{inv2.get('id')}",
                        'invoice_no': f"{inv1.get('no')} + {inv2.get('no')}",
                        'client': inv1.get(client_field, ''),
                        'amount': combined,
                        'confidence': 'combined'
                    }]
    return []

@app.route('/bank-sync')
def bank_sync():
    r = make_response(send_file('app.html'))
    r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return r

@app.route('/open-invoices', methods=['GET', 'OPTIONS'])
def open_invoices_endpoint():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    invoices = get_open_invoices('sales')
    return cors(make_response(jsonify({'invoices': invoices, 'count': len(invoices)}), 200))

@app.route('/open-purchase-invoices', methods=['GET', 'OPTIONS'])
def open_purchase_invoices_endpoint():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    invoices = get_open_invoices('purchase')
    return cors(make_response(jsonify({'invoices': invoices, 'count': len(invoices)}), 200))

@app.route('/record-payment', methods=['POST', 'OPTIONS'])
def record_payment():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    invoice_id = data.get('invoice_id')
    amount = data.get('amount')
    date = data.get('date')
    notes = data.get('notes', '')
    if not invoice_id or not amount:
        return cors(make_response(jsonify({'error': 'invoice_id and amount required'}), 400))
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        inv_resp = requests.get(f"{DAFTRA_BASE}/invoices/{invoice_id}", headers=headers, timeout=30)
        inv_data = inv_resp.json()
        invoice = inv_data.get('data', {})
        if isinstance(invoice, list):
            invoice = invoice[0] if invoice else {}
        inv = invoice.get('Invoice', invoice)
        client_id = inv.get('client_id') or inv.get('ClientId')
        unpaid = float(inv.get('summary_unpaid', 0) or 0)
        pay_amount = min(float(amount), unpaid) if unpaid > 0 else float(amount)
        payload = {"InvoicePayment": {"invoice_id": str(invoice_id), "amount": pay_amount, "date": date, "payment_method": "3", "notes": notes}}
        if client_id:
            payload["InvoicePayment"]["client_id"] = str(client_id)
        pay_resp = requests.post(f"{DAFTRA_BASE}/invoice_payments", headers=headers, json=payload, timeout=30)
        pay_data = pay_resp.json()
        if pay_resp.status_code in [200, 201] or pay_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': pay_data}), 200))
        else:
            if client_id:
                cp_payload = {"ClientPayment": {"client_id": str(client_id), "amount": float(amount), "date": date, "payment_method": "3", "notes": notes, "InvoicePayment": [{"invoice_id": str(invoice_id), "amount": pay_amount}]}}
                cp_resp = requests.post(f"{DAFTRA_BASE}/client_payments", headers=headers, json=cp_payload, timeout=30)
                if cp_resp.status_code in [200, 201] or cp_resp.json().get("result") == "successful":
                    return cors(make_response(jsonify({'success': True, 'data': cp_resp.json()}), 200))
                return cors(make_response(jsonify({'error': cp_resp.json(), 'invoice_resp': pay_data}), 400))
            return cors(make_response(jsonify({'error': pay_data}), pay_resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-purchase-payment', methods=['POST', 'OPTIONS'])
def record_purchase_payment():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    invoice_id = data.get('invoice_id')
    amount = data.get('amount')
    date = data.get('date')
    notes = data.get('notes', '')
    if not invoice_id or not amount:
        return cors(make_response(jsonify({'error': 'invoice_id and amount required'}), 400))
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        payload = {"PurchaseInvoicePayment": {"purchase_invoice_id": str(invoice_id), "amount": float(amount), "date": date, "payment_method": "3", "notes": notes}}
        resp = requests.post(f"{DAFTRA_BASE}/purchase_invoice_payments", headers=headers, json=payload, timeout=30)
        resp_data = resp.json()
        if resp.status_code in [200, 201] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-expense', methods=['POST', 'OPTIONS'])
def record_expense():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    amount = data.get('amount')
    date = data.get('date')
    description = data.get('description', '')
    category = data.get('category', 'other')
    notes = data.get('notes', '')
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        account_id = EXPENSE_ACCOUNT_ID.get(category, '54')
        rich_notes = description or ''
        if notes and notes != description:
            rich_notes = f"{description} | {notes}" if description else notes
        payload = {"Expense": {"amount": float(amount), "date": date, "description": description, "notes": rich_notes, "expense_category_id": account_id}}
        resp = requests.post(f"{DAFTRA_BASE}/expenses", headers=headers, json=payload, timeout=30)
        resp_data = resp.json()
        if resp.status_code in [200, 201, 202] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'account_id_used': account_id, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/preview-deletions', methods=['GET', 'OPTIONS'])
def preview_deletions():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    try:
        payments = fetch_all_pages('invoice_payments')
        to_delete_payments = []
        keep_payments = []
        for p in payments:
            ip = p.get('InvoicePayment', p)
            date = ip.get('date', '')
            notes = (ip.get('notes', '') or '')
            if date >= CLEANUP_CUTOFF:
                if should_exclude(notes):
                    keep_payments.append({'id': ip.get('id'), 'date': date, 'amount': ip.get('amount'), 'notes': notes[:50]})
                else:
                    to_delete_payments.append({'id': ip.get('id'), 'date': date, 'amount': ip.get('amount'), 'notes': notes[:50]})
        expenses = fetch_all_pages('expenses')
        to_delete_expenses = []
        keep_expenses = []
        for e in expenses:
            exp = e.get('Expense', e)
            date = exp.get('date', '')
            desc = (exp.get('description', '') or '')
            notes = (exp.get('notes', '') or '')
            combined = f"{desc} {notes}"
            if date >= CLEANUP_CUTOFF:
                if should_exclude(combined):
                    keep_expenses.append({'id': exp.get('id'), 'date': date, 'amount': exp.get('amount'), 'description': desc[:50]})
                else:
                    to_delete_expenses.append({'id': exp.get('id'), 'date': date, 'amount': exp.get('amount'), 'description': desc[:50]})
        return cors(make_response(jsonify({'to_delete': {'invoice_payments': to_delete_payments, 'invoice_payments_count': len(to_delete_payments), 'expenses': to_delete_expenses, 'expenses_count': len(to_delete_expenses), 'total': len(to_delete_payments) + len(to_delete_expenses)}, 'to_keep': {'invoice_payments': keep_payments, 'expenses': keep_expenses}}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/execute-deletions', methods=['POST', 'OPTIONS'])
def execute_deletions():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    try:
        headers = {'APIKEY': APIKEY}
        deleted_payments = 0
        deleted_expenses = 0
        errors = []
        payments = fetch_all_pages('invoice_payments')
        for p in payments:
            ip = p.get('InvoicePayment', p)
            date = ip.get('date', '')
            notes = (ip.get('notes', '') or '')
            if date >= CLEANUP_CUTOFF and not should_exclude(notes):
                r = requests.delete(f"{DAFTRA_BASE}/invoice_payments/{ip.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful':
                    deleted_payments += 1
                else:
                    errors.append(f"payment {ip.get('id')}: {r.text[:50]}")
        expenses = fetch_all_pages('expenses')
        for e in expenses:
            exp = e.get('Expense', e)
            date = exp.get('date', '')
            desc = (exp.get('description', '') or '')
            notes = (exp.get('notes', '') or '')
            combined = f"{desc} {notes}"
            if date >= CLEANUP_CUTOFF and not should_exclude(combined):
                r = requests.delete(f"{DAFTRA_BASE}/expenses/{exp.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful':
                    deleted_expenses += 1
                else:
                    errors.append(f"expense {exp.get('id')}: {r.text[:50]}")
        return cors(make_response(jsonify({'deleted_payments': deleted_payments, 'deleted_expenses': deleted_expenses, 'total_deleted': deleted_payments + deleted_expenses, 'errors': errors}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/analyze-bank', methods=['POST', 'OPTIONS'])
def analyze_bank():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    bank_text = data.get('text', '')
    if not bank_text:
        return cors(make_response(jsonify({'error': 'No text provided'}), 400))
    if not ANTHROPIC_KEY:
        return cors(make_response(jsonify({'error': 'No API key configured'}), 500))

    open_sales = get_open_invoices('sales')
    open_purchases = get_open_invoices('purchase')
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = """You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia.

CRITICAL RULE: Every incoming payment (direction=in) is ALWAYS a client_payment. No exceptions. Money only enters this account from clients.

CRITICAL RULE: اعمال الشوري or شركة اعمال الشوري is a client REFUND (direction=out, category=other, daftra_action=skip).

AlRajhi Bank labels internal transfers as عملية تحويل داخلية — ignore this label and classify by direction and recipient.

EMPLOYEES (classify as salary) — Official GOSI list:
عمرو محمد ديب الحلبي (ID:2229429275) = Owner → personal not salary
بلال جلال غانم (ID:2155703453) = Employee
MD ANIS (ID:2500894296), MD JAULHAS MOLLA (ID:2549846075)
محمد المجيدل (ID:1123351007), TAUFEEK AHMAD (ID:2544919612)
TAREKH HUSEN (ID:2544919596), فهد البطي (ID:1131768192)
احمد محمد حماد (ID:2568475756), فهد العليان (ID:1126192390)
RAMJAN MANSHUR (ID:2602072692), NOORUL HODA KHAN (ID:2602072783)
AFROJ SALMANI (ID:2612225173), اميرة نوح الشيخ (ID:2229429267) = Owner mother → personal
SAVEJ ABDUL RAHMAN (ID:2619122530), SADDAM KHAN (ID:2630277883)
MD ARIF HOSSAIN (ID:2630277933), WAJID ALI (ID:2636857225)
احمد الفضل (ID:1136786959), MD AMAN ULLAH (ID:2576905463)
يزن الحلبي (ID:2229429291) = Branch Manager Qassim
KAMAL HOSSAIN (ID:2551964485), SIKANDAR GUPTA (ID:2574846610) = Installation Manager Riyadh

UNOFFICIAL EMPLOYEES (salary): SALAMUDDIN, سلام مبلط, صلاح مبلط, ابو ريناد, مالك نواف, ابو حسين, عبد الله فرع الرياض, مالك, معتز or MOATAZ (former employee)

TRANSPORTATION: عبدالحسيب, عمرو علي حسن بدوي or بدوي, IBRAHIM or ابراهيم

LOCAL SUPPLIERS (match_purchase_invoice): واهوي, مصنع واهوي, أسوار الخليج, اسوار الخليج, السنا للرخام, الفرات للرخام, جنى مارين, قمم الشام

CHINA SUPPLIERS (match_purchase_invoice): GBOUEO02, SHENYANG, any China/CNY transfer

KNOWN CLIENTS (when money IN): ريميندر, مهجة, MISHARY ALZAMIL, SHARAF ALTALHI, هشام المسيند, نور البنعلى, اسامه العنزي, وليد الجحيش, سفيان الزامل, الخدمات التجارية المتكاملة, علي سعود, ماهر حباب or مؤسسة الجبر, شركة ذكي للدعاية والعلن, CAMBNI ALROMEH

OTHER: سليمان المهوس = rent Buraydah, جي مارين = rent Riyadh, LOANFLEET = loan, Mudud = salary, نقاط بيع MALI QURTOBA = client_payment, بطاقة ائتمانية or خصم مستحقات = bank_fee, قوس قزح = government PRO, Ministry of Labor = government, Expatriate Renew Iqama = government, Traffic violations = government

NOTES FIELD: Always include full details — ID numbers, employee names, reference numbers. Examples:
"تجديد إقامة - بلال جلال غانم - ID: 2155703453"
"راتب أبريل - SIKANDAR GUPTA"
"إيجار فرع بريدة - أبريل 2026"
"Ministry of Labor - رسوم تأشيرة"

daftra_action values:
- client_payment IN → "match_invoice"
- local_supplier or china_supplier OUT → "match_purchase_invoice"  
- salary/rent/transportation/government/bank_fee/personal/loan OUT → "record_expense"
- refund or unknown → "skip"

Return ONLY valid JSON:
{"bank":"","period":"","opening":0,"closing":0,"transactions":[{"date":"YYYY-MM-DD","description":"","amount":0,"direction":"in or out","category":"","party":"","daftra_action":"match_invoice or match_purchase_invoice or record_expense or skip","notes":""}]}"""

    try:
        msg = client.messages.create(
           claude-haiku-4-5-20251001
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt + "\n\n" + bank_text[:100000]}]
        )
        raw = msg.content[0].text
        m = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(m.group() if m else raw)
        transactions = result.get('transactions', [])

        for tx in transactions:
            amt = float(tx.get('amount', 0))
            party = tx.get('party', '') or ''
            description = tx.get('description', '') or ''

            # تحقق من رقم الهوية في النص
            combined = f"{party} {description}"
            emp_id = extract_id_from_text(combined)
            if emp_id and emp_id in EMPLOYEE_IDS:
                emp_name = EMPLOYEE_IDS[emp_id]
                emp_cat = EMPLOYEE_CATEGORY.get(emp_id, 'salary')
                tx['category'] = emp_cat
                tx['party'] = emp_name
                if not tx.get('notes'):
                    tx['notes'] = f"{description} - {emp_name} - ID: {emp_id}"
                tx['daftra_action'] = 'record_expense' if emp_cat in ['salary', 'personal'] else tx['daftra_action']

            if tx.get('direction') == 'in' and tx.get('category') == 'client_payment':
                matches = match_payment(amt, open_sales, party, description, 'Invoice')
                tx['invoice_matches'] = matches
                tx['daftra_action'] = 'match_invoice' if matches else 'waiting_list'

            elif tx.get('direction') == 'out' and tx.get('category') in ['local_supplier', 'china_supplier']:
                matches = match_payment(amt, open_purchases, party, description, 'PurchaseInvoice')
                tx['purchase_invoice_matches'] = matches
                tx['daftra_action'] = 'match_purchase_invoice' if matches else 'waiting_list_purchase'

        result['transactions'] = transactions
        return cors(make_response(jsonify(result), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy(endpoint):
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    url = f"{DAFTRA_BASE}/{endpoint}"
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        if request.method == 'GET':
            resp = requests.get(url, headers=headers, params=request.args, timeout=30)
        elif request.method == 'POST':
            resp = requests.post(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'PUT':
            resp = requests.put(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        return cors(make_response(jsonify(resp.json()), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/')
def health():
    return cors(make_response(jsonify({'status': 'ok'}), 200))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
