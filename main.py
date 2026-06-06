from flask import Flask, request, jsonify, make_response, send_file
import requests, os, anthropic, json, re, threading, uuid, time

app = Flask(__name__)

DAFTRA_BASE = 'https://maealequrtoba.daftra.com/api2'
APIKEY = os.environ.get('APIKEY', 'c4c035341dbe1da1531b227d89f6e2f481252766')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

_jobs = {}

def _job_path(job_id):
    return f"/tmp/job_{job_id}.json"

def _save_job(job_id, data):
    try:
        with open(_job_path(job_id), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"Save job error: {e}")

def _load_job(job_id):
    try:
        with open(_job_path(job_id), encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

CLIENT_ALIASES = {
    'سلمان عبدالعزيز': 'سلمان العودة',
    'خالد حسان': 'خالد حسان علام',
    'خالد حسين': 'خالد حسان علام',
    'سلمان العودة': 'سلمان العودة',
    'مهجة': 'ريميندر', 'reminder': 'ريميندر',
    'الخدمات التجارية المتكاملة': 'الخدمات التجارية المتكاملة',
    'خدمات متكاملة': 'الخدمات التجارية المتكاملة',
    'حباب': 'مؤسسة الجبر', 'الحباب': 'مؤسسة الجبر',
    'ماهر حباب': 'مؤسسة الجبر', 'ماهر عبدالله': 'مؤسسة الجبر',
    'الجبر': 'مؤسسة الجبر',
}

EMPLOYEE_IDS = {
    '2229429275': 'عمرو الحلبي', '2155703453': 'بلال جلال غانم',
    '2500894296': 'MD ANIS', '2549846075': 'MD JAULHAS MOLLA',
    '1123351007': 'محمد المجيدل', '2544919612': 'TAUFEEK AHMAD',
    '2544919596': 'TAREKH HUSEN', '1131768192': 'فهد البطي',
    '2568475756': 'احمد محمد حماد', '1126192390': 'فهد العليان',
    '2602072692': 'RAMJAN MANSHUR', '2602072783': 'NOORUL HODA KHAN',
    '2612225173': 'AFROJ SALMANI', '2229429267': 'اميرة',
    '2619122530': 'SAVEJ ABDUL RAHMAN', '2630277883': 'SADDAM KHAN',
    '2630277933': 'MD ARIF HOSSAIN', '2636857225': 'WAJID ALI',
    '1136786959': 'احمد الفضل', '2576905463': 'MD AMAN ULLAH',
    '2229429291': 'يزن الحلبي', '2551964485': 'KAMAL HOSSAIN',
    '2574846610': 'SIKANDAR GUPTA',
}

EMPLOYEE_CATEGORY = {
    '2229429275': 'personal', '2229429267': 'personal',
    '2155703453': 'salary', '2500894296': 'salary', '2549846075': 'salary',
    '1123351007': 'salary', '2544919612': 'salary', '2544919596': 'salary',
    '1131768192': 'salary', '2568475756': 'salary', '1126192390': 'salary',
    '2602072692': 'salary', '2602072783': 'salary', '2612225173': 'salary',
    '2619122530': 'salary', '2630277883': 'salary', '2630277933': 'salary',
    '2636857225': 'salary', '1136786959': 'salary', '2576905463': 'salary',
    '2229429291': 'salary', '2551964485': 'salary', '2574846610': 'salary',
}

ACCOUNT_TO_CLIENT = {
    '129000010006086890598': 'ريميندر', '12900608016890598': 'ريميندر',
    '200000010006080174447': 'علي سعود',
    '640000010006087461738': 'SALAMUDDIN', '077050010006087399166': 'SIKANDAR',
    '077050010006087400188': 'TAUFEEK', '697000010006086135855': 'يزن',
    '192000010006080456273': 'مالك', 'MOATAZ': 'معتز',
    '331000010006086567547': 'عبدالحسيب', 'AMRO_BADAWI': 'عمرو بدوي',
    '377000010006080000888': 'شركة السنا للرخام والسيراميك',
    '538000010006080000223': 'شركة الفرات للرخام',
    '602000010006080654780': 'شركة اسوار الخليج',
    '487000010006085245725': 'شركة هواهوي ستون',
    '487000010006080237735': 'شركة قمم الماس للتجارة',
    '599000010006080888888': 'سليمان المهوس',
    '282000010006086606237': 'مؤسسة قوس قزح',
    '077050010006084823853': 'عمرو الحلبي', '539000010006085772890': 'اميرة',
    '212000010006080319683': 'سلمان العودة',
    '555000010006080993391': 'سلطان عياد عبد الفريدي',
    '292000010006080191911': 'خالد حسان علام',
    '275000010006080071171': 'فهد عبدالله علي اليحي',
    '331000010006080115368': 'عبدالكريم محمد رياض طيارة',
    '331000010006086567547': 'عبدالحسيب',
}

ACCOUNT_CATEGORY = {
    '129000010006086890598': 'client_payment', '12900608016890598': 'client_payment',
    '200000010006080174447': 'client_payment',
    '640000010006087461738': 'salary', '077050010006087399166': 'salary',
    '077050010006087400188': 'salary', '697000010006086135855': 'salary',
    '192000010006080456273': 'salary', 'MOATAZ': 'salary',
    '331000010006086567547': 'transportation', 'AMRO_BADAWI': 'transportation',
    '377000010006080000888': 'local_supplier', '538000010006080000223': 'local_supplier',
    '602000010006080654780': 'local_supplier', '487000010006085245725': 'local_supplier',
    '599000010006080888888': 'rent', '282000010006086606237': 'government',
    '077050010006084823853': 'personal', '539000010006085772890': 'personal',
    '212000010006080319683': 'client_payment',
    '555000010006080993391': 'client_payment',
    '292000010006080191911': 'client_payment',
    '275000010006080071171': 'client_payment',
    '331000010006080115368': 'manufacturing',
}

EXPENSE_CATEGORY_ID = {
    'salary': '23',
    'rent': '19',
    'transportation': '26',
    'government': '16',
    'bank_fee': '25',
    'personal': '24',
    'loan': '10',
    'other': '24',
    'manufacturing': '1',
    'utilities': '27',
    'internet': '9',
}

# Categories that include 15% VAT (tax_id=1)
VAT_CATEGORIES = {'utilities', 'internet', 'bank_fee', 'manufacturing'}

VENDOR_NAMES = {
    'بيتي النيق': {'supplier_name': 'بيتي النيق', 'daftra_action': 'match_purchase_invoice'},
}

EXCLUDE_KEYWORDS = ['ديزل', 'محروقات', 'diesel', 'fuel']
CLEANUP_CUTOFF = '2026-04-01'
EXPENSE_CATS = ['salary', 'rent', 'transportation', 'government', 'bank_fee', 'personal', 'loan', 'manufacturing', 'utilities', 'internet', 'other']

def should_exclude(text):
    return any(kw in (text or '').lower() for kw in EXCLUDE_KEYWORDS)

def fetch_all_pages(endpoint):
    items, page = [], 1
    while True:
        r = requests.get(f"{DAFTRA_BASE}/{endpoint}", headers={'APIKEY': APIKEY},
                         params={'limit': 50, 'page': page}, timeout=30)
        data = r.json().get('data', [])
        if not data: break
        items.extend(data)
        if len(data) < 50: break
        page += 1
    return items

def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, APIKEY'
    return r

def get_open_invoices(invoice_type='sales'):
    try:
        all_invoices, endpoint = [], 'invoices' if invoice_type == 'sales' else 'purchase_invoices'
        for status in ['0', '1', '2', '3', '4']:
            page = 1
            while True:
                resp = requests.get(f"{DAFTRA_BASE}/{endpoint}", headers={'APIKEY': APIKEY},
                                    params={'payment_status': status, 'limit': 50, 'page': page})
                invoices = resp.json().get('data', [])
                if not invoices: break
                all_invoices.extend(invoices)
                if len(invoices) < 50: break
                page += 1
        seen, unique = set(), []
        key = 'Invoice' if invoice_type == 'sales' else 'PurchaseInvoice'
        for inv in all_invoices:
            inv_id = inv.get(key, {}).get('id')
            if inv_id and inv_id not in seen:
                seen.add(inv_id); unique.append(inv)
        return unique
    except:
        return []

def normalize_name(name):
    name = (name or '').lower().strip()
    for alias, canonical in CLIENT_ALIASES.items():
        if alias in name: return canonical.lower()
    return name

def extract_account_from_text(text):
    text = text or ''
    m = re.search(r'(?:FRACCT|TOACCT|FROMACCT)[/\\](\d{10,})', text)
    if m: return m.group(1)
    m = re.search(r'CA:\s*(\d{10,})', text)
    if m: return m.group(1)
    return None

def extract_id_from_text(text):
    m = re.search(r'\b([12]\d{9})\b', text or '')
    return m.group(1) if m else None

def client_name_matches(party, inv_client):
    if not party or not inv_client: return False
    acc = extract_account_from_text(party)
    if acc and acc in ACCOUNT_TO_CLIENT:
        return ACCOUNT_TO_CLIENT[acc].lower() in normalize_name(inv_client)
    p, c = normalize_name(party), normalize_name(inv_client)
    # Exact word match
    for pw in [w for w in p.split() if len(w) >= 4]:
        if pw in c: return True
    for cw in [w for w in c.split() if len(w) >= 4]:
        if cw in p: return True
    # Fuzzy: count shared words of 3+ chars
    p_words = set(w for w in p.split() if len(w) >= 3)
    c_words = set(w for w in c.split() if len(w) >= 3)
    if p_words and c_words:
        shared = len(p_words & c_words)
        score = shared / min(len(p_words), len(c_words))
        if score >= 0.5: return True
    return False

def match_payment(amount, open_invoices, party='', description='', invoice_key='Invoice'):
    combined_text = f"{party} {description}"
    acc = extract_account_from_text(combined_text)
    if acc and acc in ACCOUNT_TO_CLIENT: party = ACCOUNT_TO_CLIENT[acc]
    client_field = 'client_business_name' if invoice_key == 'Invoice' else 'supplier_name'
    client_invoices = [inv for inv in open_invoices
                       if client_name_matches(combined_text, inv.get(invoice_key, {}).get(client_field, ''))]
    # ✅ Exact amount match across ALL invoices first (regardless of name)
    for inv in open_invoices:
        inv_data = inv.get(invoice_key, {})
        unpaid = float(inv_data.get('summary_unpaid', 0) or 0)
        total = float(inv_data.get('summary_total', 0) or 0)
        inv_amount = unpaid if unpaid > 0 else total
        if inv_amount <= 0: continue
        if abs(amount - inv_amount) / inv_amount < 0.01:  # exact match < 1%
            return [{'invoice_id': inv_data.get('id'), 'invoice_no': inv_data.get('no'),
                     'client': inv_data.get(client_field, ''), 'amount': inv_amount, 'confidence': 'exact'}]
    search_pools = [client_invoices, open_invoices] if client_invoices else [open_invoices]
    for pool in search_pools:
        matches = []
        for inv in pool:
            inv_data = inv.get(invoice_key, {})
            unpaid = float(inv_data.get('summary_unpaid', 0) or 0)
            total = float(inv_data.get('summary_total', 0) or 0)
            inv_amount = unpaid if unpaid > 0 else total
            if inv_amount <= 0: continue
            diff = abs(amount - inv_amount) / inv_amount
            if diff <= 0.05:
                matches.append({'invoice_id': inv_data.get('id'), 'invoice_no': inv_data.get('no'),
                                 'client': inv_data.get(client_field, ''), 'amount': inv_amount,
                                 'confidence': 'exact' if diff < 0.01 else 'close'})
        if matches: return matches
        for i in range(len(pool)):
            for j in range(i+1, len(pool)):
                inv1, inv2 = pool[i].get(invoice_key, {}), pool[j].get(invoice_key, {})
                a1 = float(inv1.get('summary_unpaid', 0) or inv1.get('summary_total', 0) or 0)
                a2 = float(inv2.get('summary_unpaid', 0) or inv2.get('summary_total', 0) or 0)
                combined = a1 + a2
                if combined > 0 and abs(amount - combined) / combined <= 0.05:
                    return [{'invoice_id': f"{inv1.get('id')},{inv2.get('id')}",
                              'invoice_no': f"{inv1.get('no')} + {inv2.get('no')}",
                              'client': inv1.get(client_field, ''), 'amount': combined, 'confidence': 'combined'}]
    return []

BATCH_PROMPT = """You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia.
Classify the transactions below. Return ONLY valid JSON — no extra text, no markdown.

RULES:
- direction=in → ALWAYS client_payment, daftra_action=match_invoice (NO EXCEPTIONS — even 'Internal transfer in' is a client_payment)
- direction=out → classify by recipient
- 'Internal transfer in' / 'عملية تحويل داخلية' → direction=in, category=client_payment
- 'Fast transfer from' / 'حوالت سريع' with direction=in → client_payment
- description: REQUIRED — copy the raw transaction text, never leave empty
- notes: REQUIRED — include employee name + ID if salary/government, e.g. "تجديد إقامة - بلال جلال غانم - ID: 2155703453"
- daftra_action: REQUIRED — must be one of: match_invoice | match_purchase_invoice | record_expense | skip

EMPLOYEES (salary): بلال جلال غانم(2155703453), MD ANIS(2500894296), MD JAULHAS MOLLA(2549846075), محمد المجيدل(1123351007), TAUFEEK AHMAD(2544919612), TAREKH HUSEN(2544919596), فهد البطي(1131768192), احمد محمد حماد(2568475756), فهد العليان(1126192390), RAMJAN MANSHUR(2602072692), NOORUL HODA KHAN(2602072783), AFROJ SALMANI(2612225173), SAVEJ ABDUL RAHMAN(2619122530), SADDAM KHAN(2630277883), MD ARIF HOSSAIN(2630277933), WAJID ALI(2636857225), احمد الفضل(1136786959), MD AMAN ULLAH(2576905463), يزن الحلبي(2229429291), KAMAL HOSSAIN(2551964485), SIKANDAR GUPTA(2574846610), SALAMUDDIN, سلام مبلط, صلاح مبلط, ابو ريناد, مالك نواف, ابو حسين, MOATAZ
PERSONAL: عمرو الحلبي(2229429275), اميرة(2229429267)
TRANSPORT: عبدالحسيب, عمرو بدوي, IBRAHIM
LOCAL SUPPLIERS: السنا للرخام, الفرات للرخام, اسوار الخليج, هواهوي, جنى مارين, قمم الشام, بيتي النيق, قمم الماس
CHINA SUPPLIERS: GBOUEO02, SHENYANG, CNY transfers
CLIENTS: ريميندر, مهجة, MISHARY ALZAMIL, SHARAF ALTALHI, هشام المسيند, نور البنعلى, اسامه العنزي, وليد الجحيش, سفيان الزامل, الخدمات التجارية المتكاملة, علي سعود, مؤسسة الجبر, شركة ذكي للدعاية, CAMBNI ALROMEH, سلمان العودة, سلمان عبدالعزيز, خالد حسان, فهد اليحي, فهد عبدالله, عبدالله سليمان, امجد عبدالعزيز, سلطان عياد, مجمع الطب الجوهري
OTHER: طيارة/كهربائي/كهربجي/electrician=manufacturing, سليمان المهوس=rent, جي مارين=rent, LOANFLEET=loan, Mudud=salary, نقاط بيع=client_payment, بطاقة ائتمانية=bank_fee, قوس قزح=government, Ministry of Labor=government, Expatriate/Renew Iqama=government, SAUDI ELECTRIC/SEC/كهرباء=utilities, STC/زين/موبايلي/اتصالات=internet, STCPAY=internet, مياه=utilities, NWC=utilities, الاختيار الامثل/الختيار المثل/الاختيار المثل/تخليص جمركي/جمارك/customs clearance=manufacturing

category values: client_payment | local_supplier | china_supplier | salary | rent | transportation | government | bank_fee | personal | loan | other
daftra_action: in→match_invoice | supplier out→match_purchase_invoice | salary/rent/transport/gov/fee/personal/loan→record_expense | else→skip

Return ONLY: {"transactions":[{"date":"YYYY-MM-DD","description":"COPY RAW TEXT HERE","amount":0,"direction":"in","category":"","party":"","daftra_action":"record_expense","notes":"employee name - ID: XXXXXXXXXX"}]}"""

def _call_claude_batch(lines, ai_client):
    """Call Claude with a batch of transaction lines. Returns enriched list."""
    batch_text = '\n'.join(lines)
    msg = ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": BATCH_PROMPT + "\n\nTRANSACTIONS:\n" + batch_text}]
    )
    raw = msg.content[0].text
    m = re.search(r'\{[\s\S]*\}', raw)
    parsed = json.loads(m.group() if m else raw)
    txns = parsed.get('transactions', [])

    # ✅ ALWAYS use raw transaction line as description — guaranteed to have real text
    # ✅ Fix: remap 'internal' to client_payment for incoming transactions
    for tx in txns:
        if tx.get('category') in ('internal', 'transfer', 'internal_transfer') and tx.get('direction') == 'in':
            tx['category'] = 'client_payment'
            tx['daftra_action'] = 'match_invoice'

    CATEGORY_WORDS = {'salary','rent','transportation','government','bank_fee','personal','loan',
                      'other','رواتب','إيجار','نقل','حكومي','رسوم','شخصي','قرض','أخرى',
                      'client_payment','local_supplier','china_supplier','record_expense','skip'}
    for i, tx in enumerate(txns):
        raw_line = lines[i] if i < len(lines) else ''
        claude_desc = (tx.get('description') or '').strip()
        # If Claude returned empty or just a category word, use raw line
        if not claude_desc or claude_desc.lower() in CATEGORY_WORDS:
            tx['description'] = raw_line
        else:
            tx['description'] = claude_desc
        # Notes: combine Claude's description with raw line for full context
        tx['notes'] = claude_desc if claude_desc and claude_desc.lower() not in CATEGORY_WORDS else raw_line
        if not (tx.get('daftra_action') or '').strip():
            cat = tx.get('category', '')
            if tx.get('direction') == 'in':
                tx['daftra_action'] = 'match_invoice'
            elif cat in EXPENSE_CATS:
                tx['daftra_action'] = 'record_expense'
            elif cat in ['local_supplier', 'china_supplier']:
                tx['daftra_action'] = 'match_purchase_invoice'
            else:
                tx['daftra_action'] = 'skip'
    return txns

def _enrich_transactions(transactions, open_sales, open_purchases):
    for tx in transactions:
        amt = float(tx.get('amount', 0))
        party = tx.get('party', '') or ''
        description = tx.get('description', '') or ''
        combined = f"{party} {description}"

        for vendor_key, vendor_info in VENDOR_NAMES.items():
            if vendor_key in combined:
                tx['category'] = 'local_supplier'
                tx['party'] = vendor_info['supplier_name']
                tx['daftra_action'] = vendor_info['daftra_action']
                break

        emp_id = extract_id_from_text(combined)
        if emp_id and emp_id in EMPLOYEE_IDS:
            emp_name = EMPLOYEE_IDS[emp_id]
            emp_cat = EMPLOYEE_CATEGORY.get(emp_id, 'salary')
            tx['category'] = emp_cat
            tx['party'] = emp_name
            tx['notes'] = f"{description} - {emp_name} - ID: {emp_id}"
            tx['daftra_action'] = 'record_expense'

        if tx.get('direction') == 'in' and tx.get('category') == 'client_payment':
            matches = match_payment(amt, open_sales, party, description, 'Invoice')
            tx['invoice_matches'] = matches
            tx['daftra_action'] = 'match_invoice' if matches else 'waiting_list'
        elif tx.get('direction') == 'out' and tx.get('category') in ['local_supplier', 'china_supplier']:
            matches = match_payment(amt, open_purchases, party, description, 'PurchaseInvoice')
            tx['purchase_invoice_matches'] = matches
            tx['daftra_action'] = 'match_purchase_invoice' if matches else 'waiting_list_purchase'
    return transactions

def _do_analysis(bank_text):
    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    header_lines = bank_text.split('\n')[:10]
    try:
        hdr_msg = ai_client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=200,
            messages=[{"role": "user", "content": 'Extract bank name, period, opening balance, closing balance. Return ONLY JSON: {"bank":"","period":"","opening":0,"closing":0}\n\n' + '\n'.join(header_lines)}]
        )
        hm = re.search(r'\{[^}]+\}', hdr_msg.content[0].text)
        header = json.loads(hm.group()) if hm else {"bank": "الراجحي", "period": "", "opening": 0, "closing": 0}
    except:
        header = {"bank": "الراجحي", "period": "", "opening": 0, "closing": 0}

    all_lines = [l.strip() for l in bank_text.split('\n') if l.strip()]
    tx_lines = [l for l in all_lines if re.search(r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}', l)]
    if not tx_lines: tx_lines = all_lines

    BATCH_SIZE = 15
    batches = [tx_lines[i:i+BATCH_SIZE] for i in range(0, len(tx_lines), BATCH_SIZE)]
    all_transactions = []
    for batch in batches:
        try:
            all_transactions.extend(_call_claude_batch(batch, ai_client))
        except:
            continue

    needs_sales = any(t.get('direction') == 'in' and t.get('category') == 'client_payment' for t in all_transactions)
    needs_purchases = any(t.get('direction') == 'out' and t.get('category') in ['local_supplier', 'china_supplier'] for t in all_transactions)
    open_sales = get_open_invoices('sales') if needs_sales else []
    open_purchases = get_open_invoices('purchase') if needs_purchases else []
    all_transactions = _enrich_transactions(all_transactions, open_sales, open_purchases)
    return {**header, 'transactions': all_transactions}

def _run_analysis(job_id, bank_text):
    try:
        _save_job(job_id, {'status': 'running'})
        result = _do_analysis(bank_text)
        _save_job(job_id, {'status': 'done', 'result': result})
    except Exception as e:
        _save_job(job_id, {'status': 'error', 'error': str(e)})

@app.route('/bank-sync')
def bank_sync():
    r = make_response(send_file('app.html'))
    r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return r

@app.route('/open-invoices', methods=['GET', 'OPTIONS'])
def open_invoices_endpoint():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    return cors(make_response(jsonify({'invoices': get_open_invoices('sales')}), 200))

@app.route('/open-purchase-invoices', methods=['GET', 'OPTIONS'])
def open_purchase_invoices_endpoint():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    return cors(make_response(jsonify({'invoices': get_open_invoices('purchase')}), 200))

@app.route('/analyze-batch', methods=['POST', 'OPTIONS'])
def analyze_batch_endpoint():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    lines = data.get('lines', [])
    is_first = data.get('is_first', False)
    header_text = data.get('header_text', '')
    if not lines: return cors(make_response(jsonify({'transactions': []}), 200))
    if not ANTHROPIC_KEY: return cors(make_response(jsonify({'error': 'No API key'}), 500))
    try:
        ai_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        txns = _call_claude_batch(lines, ai_client)
        result = {'transactions': txns}
        if is_first and header_text:
            try:
                hdr_msg = ai_client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=200,
                    messages=[{"role": "user", "content": 'Extract bank, period, opening, closing. Return ONLY JSON: {"bank":"","period":"","opening":0,"closing":0}\n\n' + header_text}]
                )
                hm = re.search(r'\{[^}]+\}', hdr_msg.content[0].text)
                if hm: result.update(json.loads(hm.group()))
            except: pass
        return cors(make_response(jsonify(result), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e), 'transactions': []}), 200))

@app.route('/analyze-bank-sync', methods=['POST', 'OPTIONS'])
def analyze_bank_sync():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    bank_text = data.get('text', '')
    if not bank_text: return cors(make_response(jsonify({'error': 'No text provided'}), 400))
    if not ANTHROPIC_KEY: return cors(make_response(jsonify({'error': 'No API key configured'}), 500))
    try:
        result = _do_analysis(bank_text)
        return cors(make_response(jsonify({'status': 'done', 'result': result}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'status': 'error', 'error': str(e)}), 500))

@app.route('/analyze-bank', methods=['POST', 'OPTIONS'])
def analyze_bank():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    bank_text = data.get('text', '')
    if not bank_text: return cors(make_response(jsonify({'error': 'No text provided'}), 400))
    if not ANTHROPIC_KEY: return cors(make_response(jsonify({'error': 'No API key configured'}), 500))
    job_id = str(uuid.uuid4())
    _save_job(job_id, {'status': 'pending'})
    threading.Thread(target=_run_analysis, args=(job_id, bank_text), daemon=True).start()
    return cors(make_response(jsonify({'job_id': job_id, 'status': 'pending'}), 200))

@app.route('/analysis-result/<job_id>', methods=['GET', 'OPTIONS'])
def analysis_result(job_id):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    job = _load_job(job_id)
    if not job: return cors(make_response(jsonify({'status': 'not_found'}), 404))
    return cors(make_response(jsonify(job), 200))

@app.route('/record-payment', methods=['POST', 'OPTIONS'])
def record_payment():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    invoice_id, amount, date, notes = data.get('invoice_id'), data.get('amount'), data.get('date'), data.get('notes', '')
    if not invoice_id or not amount: return cors(make_response(jsonify({'error': 'invoice_id and amount required'}), 400))
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        inv_resp = requests.get(f"{DAFTRA_BASE}/invoices/{invoice_id}", headers=headers, timeout=30)
        inv_data = inv_resp.json().get('data', {})
        if isinstance(inv_data, list): inv_data = inv_data[0] if inv_data else {}
        inv = inv_data.get('Invoice', inv_data)
        client_id = inv.get('client_id') or inv.get('ClientId')
        unpaid = float(inv.get('summary_unpaid', 0) or 0)
        pay_amount = min(float(amount), unpaid) if unpaid > 0 else float(amount)
        payload = {"InvoicePayment": {"invoice_id": str(invoice_id), "amount": pay_amount, "date": date, "payment_method": "3", "notes": notes}}
        if client_id: payload["InvoicePayment"]["client_id"] = str(client_id)
        pay_resp = requests.post(f"{DAFTRA_BASE}/invoice_payments", headers=headers, json=payload, timeout=30)
        pay_data = pay_resp.json()
        if pay_resp.status_code in [200, 201] or pay_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': pay_data}), 200))
        if client_id:
            cp_resp = requests.post(f"{DAFTRA_BASE}/client_payments", headers=headers, timeout=30,
                json={"ClientPayment": {"client_id": str(client_id), "amount": float(amount), "date": date,
                                        "payment_method": "3", "notes": notes,
                                        "InvoicePayment": [{"invoice_id": str(invoice_id), "amount": pay_amount}]}})
            if cp_resp.status_code in [200, 201] or cp_resp.json().get("result") == "successful":
                return cors(make_response(jsonify({'success': True, 'data': cp_resp.json()}), 200))
        return cors(make_response(jsonify({'error': pay_data}), pay_resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-purchase-payment', methods=['POST', 'OPTIONS'])
def record_purchase_payment():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        resp = requests.post(f"{DAFTRA_BASE}/purchase_invoice_payments", headers=headers, timeout=30,
            json={"PurchaseInvoicePayment": {"purchase_invoice_id": str(data.get('invoice_id')),
                                              "amount": float(data.get('amount')), "date": data.get('date'),
                                              "payment_method": "3", "notes": data.get('notes', '')}})
        resp_data = resp.json()
        if resp.status_code in [200, 201] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-expense', methods=['POST', 'OPTIONS'])
def record_expense():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    amount = data.get('amount')
    date = data.get('date')
    description = data.get('description', '') or ''
    category = data.get('category', 'other')
    notes = data.get('notes', '') or ''
    expense_category_id = EXPENSE_CATEGORY_ID.get(category, '24')
    # Always ensure description is not empty
    if not description.strip():
        description = notes or 'مصروف'
    rich_notes = f"{description} | {notes}" if notes and notes != description else (description or notes)
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        expense_payload = {
            "amount": float(amount),
            "date": date,
            "note": rich_notes,
            "expense_category_id": expense_category_id,
            "treasury_id": "3"
        }
        if category in VAT_CATEGORIES:
            expense_payload["ExpenseTax"] = [{"tax_id": "1", "tax_amount": round(float(amount) * 0.15, 2)}]
        resp = requests.post(f"{DAFTRA_BASE}/expenses", headers=headers, timeout=30,
            json={"Expense": expense_payload})
        resp_data = resp.json()
        if resp.status_code in [200, 201, 202] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/edit-expense/<expense_id>', methods=['PUT', 'OPTIONS'])
def edit_expense(expense_id):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    category = data.get('category', 'other')
    expense_category_id = EXPENSE_CATEGORY_ID.get(category, '24')
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        payload = {"Expense": {"expense_category_id": expense_category_id}}
        if 'description' in data: payload['Expense']['description'] = data['description']
        if 'amount' in data: payload['Expense']['amount'] = float(data['amount'])
        if 'date' in data: payload['Expense']['date'] = data['date']
        if 'notes' in data: payload['Expense']['notes'] = data['notes']
        resp = requests.put(f"{DAFTRA_BASE}/expenses/{expense_id}", headers=headers, json=payload, timeout=30)
        resp_data = resp.json()
        if resp.status_code in [200, 201] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/preview-deletions', methods=['GET', 'OPTIONS'])
def preview_deletions():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    try:
        to_del_p, keep_p = [], []
        for p in fetch_all_pages('invoice_payments'):
            ip = p.get('InvoicePayment', p)
            d, n = ip.get('date', ''), ip.get('notes', '') or ''
            if d >= CLEANUP_CUTOFF:
                (keep_p if should_exclude(n) else to_del_p).append({'id': ip.get('id'), 'date': d, 'amount': ip.get('amount'), 'notes': n[:50]})
        to_del_e, keep_e = [], []
        for e in fetch_all_pages('expenses'):
            exp = e.get('Expense', e)
            d = exp.get('date', '')
            desc, n = exp.get('description', '') or '', exp.get('notes', '') or ''
            if d >= CLEANUP_CUTOFF:
                (keep_e if should_exclude(f"{desc} {n}") else to_del_e).append({'id': exp.get('id'), 'date': d, 'amount': exp.get('amount'), 'description': desc[:50]})
        return cors(make_response(jsonify({'to_delete': {'invoice_payments': to_del_p, 'invoice_payments_count': len(to_del_p), 'expenses': to_del_e, 'expenses_count': len(to_del_e), 'total': len(to_del_p)+len(to_del_e)}, 'to_keep': {'invoice_payments': keep_p, 'expenses': keep_e}}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/execute-deletions', methods=['POST', 'OPTIONS'])
def execute_deletions():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    try:
        headers, del_p, del_e, errors = {'APIKEY': APIKEY}, 0, 0, []
        for p in fetch_all_pages('invoice_payments'):
            ip = p.get('InvoicePayment', p)
            if ip.get('date', '') >= CLEANUP_CUTOFF and not should_exclude(ip.get('notes', '') or ''):
                r = requests.delete(f"{DAFTRA_BASE}/invoice_payments/{ip.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful': del_p += 1
                else: errors.append(f"payment {ip.get('id')}: {r.text[:50]}")
        for e in fetch_all_pages('expenses'):
            exp = e.get('Expense', e)
            desc, n = exp.get('description', '') or '', exp.get('notes', '') or ''
            if exp.get('date', '') >= CLEANUP_CUTOFF and not should_exclude(f"{desc} {n}"):
                r = requests.delete(f"{DAFTRA_BASE}/expenses/{exp.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful': del_e += 1
                else: errors.append(f"expense {exp.get('id')}: {r.text[:50]}")
        return cors(make_response(jsonify({'deleted_payments': del_p, 'deleted_expenses': del_e, 'total_deleted': del_p+del_e, 'errors': errors}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/find-invoice/<invoice_no>', methods=['GET', 'OPTIONS'])
def find_invoice(invoice_no):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    try:
        r = requests.get(f"{DAFTRA_BASE}/invoices/{invoice_no}", headers={'APIKEY': APIKEY}, timeout=15)
        data = r.json()
        inv = data.get('data', {})
        if isinstance(inv, list): inv = inv[0] if inv else {}
        inv_obj = inv.get('Invoice', inv)
        if inv_obj.get('id'):
            return cors(make_response(jsonify({'found': True, 'invoice': inv_obj}), 200))
        search = requests.get(f"{DAFTRA_BASE}/invoices", headers={'APIKEY': APIKEY},
                              params={'no': invoice_no, 'limit': 5}, timeout=15)
        results = search.json().get('data', [])
        for item in results:
            i = item.get('Invoice', item)
            if i.get('no') == invoice_no or i.get('no') == invoice_no.lstrip('0') or str(i.get('id')) == invoice_no:
                return cors(make_response(jsonify({'found': True, 'invoice': i}), 200))
        return cors(make_response(jsonify({'found': False}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))


@app.route('/record-client-payment', methods=['POST', 'OPTIONS'])
def record_client_payment():
    """Record a payment for a client — creates client if not found, then records payment."""
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    amount = data.get('amount')
    date = data.get('date')
    party = data.get('party', '') or ''
    notes = data.get('notes', '') or ''
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        # Step 1: Search for existing client
        client_id = None
        search = requests.get(f"{DAFTRA_BASE}/clients", headers=headers,
                              params={'business_name': party, 'limit': 5}, timeout=15)
        clients = search.json().get('data', [])
        for c in clients:
            cl = c.get('Client', c)
            name = (cl.get('business_name') or cl.get('name') or '').strip()
            if name and (name in party or party in name):
                client_id = cl.get('id')
                break

        # Step 2: Create client if not found
        if not client_id:
            create_resp = requests.post(f"{DAFTRA_BASE}/clients", headers=headers, timeout=15,
                json={"Client": {"business_name": party, "type": "1"}})
            create_data = create_resp.json()
            client_id = (create_data.get('data') or {}).get('id') or create_data.get('id')

        if not client_id:
            return cors(make_response(jsonify({'error': 'Could not create client'}), 500))

        # Step 3: Record client payment (advance payment, no invoice)
        pay_resp = requests.post(f"{DAFTRA_BASE}/client_payments", headers=headers, timeout=30,
            json={"ClientPayment": {
                "client_id": str(client_id),
                "amount": float(amount),
                "date": date,
                "payment_method": "3",
                "treasury_id": "3",
                "notes": notes or party
            }})
        pay_data = pay_resp.json()
        if pay_resp.status_code in [200, 201] or pay_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'client_id': client_id, 'data': pay_data}), 200))
        return cors(make_response(jsonify({'error': pay_data}), pay_resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy(endpoint):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    url = f"{DAFTRA_BASE}/{endpoint}"
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        if request.method == 'GET': resp = requests.get(url, headers=headers, params=request.args, timeout=30)
        elif request.method == 'POST': resp = requests.post(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'PUT': resp = requests.put(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'DELETE': resp = requests.delete(url, headers=headers, timeout=30)
        return cors(make_response(jsonify(resp.json()), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/')
def health():
    return cors(make_response(jsonify({'status': 'ok'}), 200))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
