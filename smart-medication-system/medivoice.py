"""
MediVoice Multilingual Conversational AI Assistant Service
Supports English (en-IN), Hindi (hi-IN), Telugu (te-IN), and Tamil (ta-IN).
Handles natural language intent parsing, application usage guidance,
database grounding, medical safety guardrails, and role-based data isolation.
"""

import os
import re
from datetime import date, datetime, timedelta

# Check for optional external LLM key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Supported Languages Mapping
SUPPORTED_LANGUAGES = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "te-IN": "Telugu",
    "ta-IN": "Tamil"
}

# Language script detection
def detect_language(text, explicit_lang=None):
    """
    Detects language from text script or falls back to explicit_lang / en-IN.
    """
    if not text:
        return explicit_lang if explicit_lang in SUPPORTED_LANGUAGES else "en-IN"

    # Unicode block ranges
    # Devanagari (Hindi): \u0900 - \u097F
    if re.search(r'[\u0900-\u097F]', text):
        return "hi-IN"
    # Telugu: \u0C00 - \u0C7F
    if re.search(r'[\u0C00-\u0C7F]', text):
        return "te-IN"
    # Tamil: \u0B80 - \u0BFF
    if re.search(r'[\u0B80-\u0BFF]', text):
        return "ta-IN"

    if explicit_lang and explicit_lang in SUPPORTED_LANGUAGES:
        return explicit_lang

    return "en-IN"


def process_medivoice_query(user_text, user_id, user_role, db_conn, target_patient_id=None, requested_lang=None):
    """
    Processes a natural language query in English, Hindi, Telugu, or Tamil.
    Guarantees strict data isolation:
    - If user_role == 'patient', query MUST only inspect records for user_id.
    - If user_role == 'caregiver', query MUST only inspect explicitly authorized patients.
    Returns:
    {
        "reply": str,
        "action": dict or None,
        "mode": "rule_based" or "safety_guardrail" or "app_guide",
        "lang": str,
        "authorized": bool
    }
    """
    raw_text = (user_text or "").strip()
    lang = detect_language(raw_text, requested_lang)
    text = raw_text.lower()
    today_str = date.today().strftime("%Y-%m-%d")

    # Empty text prompt
    if not text:
        replies = {
            "en-IN": "I'm listening. You can speak or type in English, Hindi, Telugu, or Tamil. Ask about your medicines, adherence rate, or how to use the system.",
            "hi-IN": "मैं सुन रहा हूँ। आप अपनी आज की दवाओं, अनुपालन (adherence), या सिस्टम का उपयोग कैसे करें के बारे में पूछ सकते हैं।",
            "te-IN": "నేను వింటున్నాను. మీ నేటి మందులు, అడ్హీరెన్స్ శాతం, లేదా అప్లికేషన్ ఎలా ఉపయోగించాలో నన్ను అడగవచ్చు.",
            "ta-IN": "நான் கேட்கிறேன். உங்கள் இன்றைய மருந்துகள், பின்பற்றும் வீதம், அல்லது செயலியை எவ்வாறு பயன்படுத்துவது என்பதைப் பற்றி நீங்கள் கேட்கலாம்."
        }
        return {
            "reply": replies.get(lang, replies["en-IN"]),
            "action": None,
            "mode": "rule_based",
            "lang": lang,
            "authorized": True
        }

    # =========================================================================
    # 1. MEDICAL SAFETY & EMERGENCY GUARDRAILS (Highest Priority)
    # =========================================================================
    emergency_patterns = [
        # English
        "chest pain", "shortness of breath", "can't breathe", "cannot breathe",
        "overdose", "poison", "unconscious", "emergency", "severe allergic",
        "anaphylaxis", "heart attack", "stroke",
        # Hindi
        "छाती में दर्द", "सीने में दर्द", "सांस लेने में तकलीफ", "सांस नहीं", "आपातकालीन", "बेहोश",
        # Telugu
        "ఛాతీ నొప్పి", "శ్వాస తీసుకోవడంలో ఇబ్బంది", "శ్వాస ఆడట్లేదు", "అత్యవసర", "గుండెపోటు",
        # Tamil
        "நெஞ்சு வலி", "மூச்சுத் திணறல்", "மூச்சு விட முடியவில்லை", "அவசரம்", "மாரடைப்பு"
    ]
    if any(p in text for p in emergency_patterns):
        safety_replies = {
            "en-IN": "🚨 IMPORTANT: If you are experiencing a medical emergency, severe chest pain, shortness of breath, or an allergic reaction, please immediately contact your local emergency services (such as 112 or 911) or visit the nearest emergency room immediately.",
            "hi-IN": "🚨 महत्वपूर्ण सूचना: यदि आपको सीने में तेज दर्द, सांस लेने में तकलीफ या कोई गंभीर आपातकालीन समस्या है, तो कृपया तुरंत स्थानीय आपातकालीन सेवा (112) पर संपर्क करें या नजदीकी अस्पताल के आपातकालीन विभाग में जाएं।",
            "te-IN": "🚨 ముఖ్యమైన హెచ్చరిక: మీకు తీవ్రమైన ఛాతీ నొప్పి, శ్వాస ఆడకపోవడం లేదా ఇతర వైద్య అత్యవసర పరిస్థితి ఉంటే, దయచేసి వెంటనే అత్యవసర సేవలకు (112) కాల్ చేయండి లేదా సమీపంలోని ఆసుపత్రికి వెళ్లండి.",
            "ta-IN": "🚨 முக்கிய அறிவிப்பு: உங்களுக்கு கடுமையான நெஞ்சு வலி, மூச்சுத் திணறல் அல்லது மருத்துவ அவசரநிலை ஏற்பட்டால், உடனடியாக உள்ளூர் அவசர சிகிச்சை பிரிவை (112) தொடர்பு கொள்ளவும் அல்லது அருகிலுள்ள மருத்துவமனைக்கு செல்லவும்."
        }
        return {
            "reply": safety_replies.get(lang, safety_replies["en-IN"]),
            "action": None,
            "mode": "safety_guardrail",
            "lang": lang,
            "authorized": True
        }

    dosage_change_patterns = [
        # English
        "stop taking", "stop my medicine", "increase dose", "decrease dose",
        "double my dose", "change dosage", "change my dose", "skip medicine",
        # Hindi
        "दवा बंद", "डोज़ बढ़ा", "डोज़ कम", "दवा बदल", "दवा छोड़",
        # Telugu
        "మందు ఆపవచ్చా", "డోస్ మార్చవచ్చా", "డోస్ పెంచవచ్చా", "మందు మానేయవచ్చా",
        # Tamil
        "மருந்தை நிறுத்தலாமா", "அளவை மாற்றலாமா", "மருந்தை தவிர்க்கலாமா"
    ]
    if any(p in text for p in dosage_change_patterns):
        dosage_replies = {
            "en-IN": "⚠️ For your safety, MediVoice cannot recommend changing dosages or stopping prescribed medicines. Please consult your prescribing doctor or pharmacist before making any modifications to your schedule.",
            "hi-IN": "⚠️ आपकी सुरक्षा के लिए, MediVoice दवाओं की खुराक बदलने या बंद करने की सलाह नहीं दे सकता। कृपया अपने डॉक्टर या फार्मासिस्ट से परामर्श लें।",
            "te-IN": "⚠️ మీ భద్రత కోసం, MediVoice మందుల మోతాదును మార్చడానికి లేదా ఆపడానికి సలహా ఇవ్వదు. దయచేసి మార్పులు చేసే ముందు మీ వైద్యుడిని సంప్రదించండి.",
            "ta-IN": "⚠️ உங்கள் பாதுகாப்பிற்காக, மருந்து அளவை மாற்றவோ அல்லது நிறுத்தவோ MediVoice பரிந்துரைக்க முடியாது. எந்தவொரு மாற்றத்திற்கும் உங்கள் மருத்துவரை அணுகவும்."
        }
        return {
            "reply": dosage_replies.get(lang, dosage_replies["en-IN"]),
            "action": None,
            "mode": "safety_guardrail",
            "lang": lang,
            "authorized": True
        }

    # =========================================================================
    # 2. APPLICATION USAGE & FEATURE GUIDE (Multilingual Knowledge Base)
    # =========================================================================
    # Check if query is asking how to use the app, add meds, mark taken, view history, etc.

    # A. How to use application / Dashboard explanation
    app_guide_patterns = [
        "how do i use this application", "how to use this app", "how does this app work", "how do i use this system",
        "explain my dashboard", "explain the dashboard", "what is this system", "how does it work", "how to use",
        "इस ऐप का उपयोग कैसे करें", "सिस्टम कैसे काम करता है", "डैशबोर्ड समझाएं", "उपयोग कैसे करें", "कैसे चलाएं",
        "ఈ యాప్ ఎలా ఉపయోగించాలి", "డ్యాష్‌బోర్డ్ వివరించండి", "ఈ సిస్టమ్ ఎలా పనిచేస్తుంది", "ఎలా ఉపయోగించాలి", "ఎలా వాడాలి", "సిస్టమ్‌ను ఎలా",
        "இந்த செயலியை எப்படி பயன்படுத்துவது", "டாஷ்போர்டை விளக்குங்கள்", "இது எப்படி வேலை செய்கிறது", "எப்படி பயன்படுத்துவது", "செயலியை எவ்வாறு"
    ]
    if any(p in text for p in app_guide_patterns):
        guide_replies = {
            "en-IN": "Welcome to the Smart Medication Adherence System! 1. Check 'Today's Medications' on your dashboard to see medicines due today. 2. When a dose is due, click 'Test Reminder' to confirm it as TAKEN or MISSED. 3. Use '+ Add Medication' in the top menu to schedule new prescriptions. 4. Visit 'Adherence History' to view your 7-day adherence charts. You can also talk to me anytime by clicking the microphone!",
            "hi-IN": "स्मार्ट मेडिकेशन सिस्टम में आपका स्वागत है! 1. आज की दवाएं देखने के लिए डैशबोर्ड पर 'Today's Medications' देखें। 2. जब दवा का समय हो, तो 'Test Reminder' पर क्लिक करके TAKEN (ली गई) या MISSED (छूटी हुई) चुनें। 3. नई दवा जोड़ने के लिए ऊपर '+ Add Medicine' बटन दबाएं। 4. 'Adherence History' में अपना साप्ताहिक चार्ट देखें। आप मुझसे कभी भी माइक दबाकर बात कर सकते हैं!",
            "te-IN": "స్మార్ట్ మెడికేషన్ సిస్టమ్‌కు స్వాగతం! 1. ఈరోజు తీసుకోవాల్సిన మందులను డ్యాష్‌బోర్డ్‌లో చూడండి. 2. మందు వేసుకున్నప్పుడు 'Test Reminder' పై క్లిక్ చేసి TAKEN లేదా MISSED అని నిర్ధారించండి. 3. కొత్త మందును చేర్చడానికి '+ Add Medicine' బటన్ నొక్కండి. 4. 'Adherence History' లో మీ చార్ట్‌లను చూడండి. మాట్లాడటానికి ఎప్పుడైనా మైక్ బటన్ నొక్కవచ్చు!",
            "ta-IN": "ஸ்மார்ட் மருந்து மேலாண்மை அமைப்புக்கு வரவேற்கிறோம்! 1. இன்றைய மருந்துகளை டாஷ்போர்டில் பார்க்கலாம். 2. மருந்து எடுத்தவுடன் 'Test Reminder' கிளிக் செய்து TAKEN அல்லது MISSED என உறுதிப்படுத்தவும். 3. புதிய மருந்தை சேர்க்க '+ Add Medicine' பொத்தானை அழுத்தவும். 4. 'Adherence History' பக்கத்தில் வாராந்திர விளக்கப்படத்தை பார்க்கலாம். பேச எப்போது வேண்டுமானாலும் மைக் பொத்தானை அழுத்தவும்!"
        }
        return {
            "reply": guide_replies.get(lang, guide_replies["en-IN"]),
            "action": None,
            "mode": "app_guide",
            "lang": lang,
            "authorized": True
        }

    # B. How to add a medicine
    add_med_patterns = [
        "how do i add a new medicine", "how to add a medicine", "how can i add a medicine", "add a medicine", "add medicine",
        "दवा कैसे जोड़ें", "नई दवा कैसे जोड़ूँ", "दवा जोड़ना",
        "కొత్త మందును ఎలా జోడించాలి", "మందును ఎలా యాడ్ చేయాలి", "మందు ఎలా చేర్చాలి",
        "புதிய மருந்தை எப்படி சேர்ப்பது", "மருந்தை எவ்வாறு சேர்ப்பது", "மருந்து சேர்க்க"
    ]
    if any(p in text for p in add_med_patterns):
        add_replies = {
            "en-IN": "To add a new medicine: 1. Click '+ Add Medicine' in the navigation bar. 2. Enter Medicine Name, prescribed Dosage, Frequency, and Scheduled Time (e.g., 08:00 AM). 3. Choose Start Date and End Date, with optional instructions. 4. Click 'Save Medication'. It will immediately appear in your daily schedule!",
            "hi-IN": "नई दवा जोड़ने के लिए: 1. ऊपर नेविगेशन बार में '+ Add Medicine' पर क्लिक करें। 2. दवा का नाम, खुराक (Dosage), आवृत्ति (Frequency) और समय (जैसे 08:00 AM) भरें। 3. प्रारंभ और समाप्ति तिथि चुनें। 4. 'Save Medication' पर क्लिक करें। यह तुरंत आपकी आज की सूची में जुड़ जाएगी!",
            "te-IN": "కొత్త మందును జోడించడానికి: 1. మెనూలో '+ Add Medicine' పై క్లిక్ చేయండి. 2. మందు పేరు, మోతాదు (Dosage), ఫ్రీక్వెన్సీ మరియు సమయం (ఉదా: 08:00 AM) నమోదు చేయండి. 3. ప్రారంభ మరియు ముగింపు తేదీలను ఎంచుకోండి. 4. 'Save Medication' పై క్లిక్ చేయండి. ఇది వెంటనే మీ షెడ్యూల్‌లో కనిపిస్తుంది!",
            "ta-IN": "புதிய மருந்தை சேர்க்க: 1. மெனுவில் '+ Add Medicine' என்பதை கிளிக் செய்யவும். 2. மருந்தின் பெயர், அளவு (Dosage), நேரம் (எ.கா. 08:00 AM) உள்ளிடவும். 3. தொடக்க மற்றும் முடிவு தேதியை தேர்வு செய்யவும். 4. 'Save Medication' என்பதை கிளிக் செய்யவும். அது உடனே உங்கள் அட்டவணையில் தோன்றும்!"
        }
        return {
            "reply": add_replies.get(lang, add_replies["en-IN"]),
            "action": {"type": "navigate", "url": "/medications/add"},
            "mode": "app_guide",
            "lang": lang,
            "authorized": True
        }

    # C. How to mark medicine as taken / missed
    mark_taken_patterns = [
        "how do i mark my medicine as taken", "how to mark medicine taken", "how to confirm a dose", "how to use reminders",
        "दवा ली गई कैसे मार्क करें", "दवा की पुष्टि कैसे करें", "दवा ले ली कैसे बताएं",
        "మందు తీసుకున్నట్లు ఎలా గుర్తించాలి", "మందు వేసుకున్నట్లు ఎలా నమోదు చేయాలి",
        "மருந்து எடுத்ததாக எப்படி குறிப்பது", "மருந்தை உறுதிப்படுத்துவது எப்படி"
    ]
    if any(p in text for p in mark_taken_patterns):
        taken_replies = {
            "en-IN": "To record a dose: 1. In 'Today's Medications' table, locate the medicine. 2. Click the '🔔 Test Reminder' button to trigger the confirmation modal immediately. 3. Click '[ ✓ TAKEN ]' if you took it, or '[ ✕ MISSED ]' if you missed it. You can also simply say: 'I took Paracetamol' to me!",
            "hi-IN": "दवा की पुष्टि करने के लिए: 1. 'Today's Medications' टेबल में अपनी दवा देखें। 2. 'Test Reminder' बटन पर क्लिक करें। 3. यदि आपने दवा ली है तो '[ ✓ TAKEN ]' दबाएं, यदि छूट गई है तो '[ ✕ MISSED ]' दबाएं। आप मुझसे सीधे 'I took my medicine' भी कह सकते हैं!",
            "te-IN": "మందును నమోదు చేయడానికి: 1. 'Today's Medications' పట్టికలో మందు పక్కన ఉన్న 'Test Reminder' బటన్ నొక్కండి. 2. మీరు మందు తీసుకుంటే '[ ✓ TAKEN ]' నొక్కండి, మిస్ అయితే '[ ✕ MISSED ]' నొక్కండి. లేదా మీరు నాతో 'I took my medicine' అని నేరుగా చెప్పవచ్చు!",
            "ta-IN": "மருந்தை பதிவு செய்ய: 1. அட்டவணையில் 'Test Reminder' பொத்தானை அழுத்தவும். 2. மருந்து எடுத்திருந்தால் '[ ✓ TAKEN ]' அல்லது தவறவிட்டால் '[ ✕ MISSED ]' என்பதை அழுத்தவும். அல்லது என்னிடம் 'I took my medicine' என்றும் கூறலாம்!"
        }
        return {
            "reply": taken_replies.get(lang, taken_replies["en-IN"]),
            "action": None,
            "mode": "app_guide",
            "lang": lang,
            "authorized": True
        }

    # D. How to change language / voice settings
    lang_help_patterns = [
        "how do i change the language", "how to change language", "change voice", "mute voice",
        "भाषा कैसे बदलें", "आवाज़ कैसे बदलें",
        "భాషను ఎలా మార్చాలి", "వాయిస్ ఎలా మార్చాలి",
        "மொழியை எப்படி மாற்றுவது", "குரலை எப்படி மாற்றுவது"
    ]
    if any(p in text for p in lang_help_patterns):
        lang_replies = {
            "en-IN": "To change the language: Select English, Hindi (हिन्दी), Telugu (తెలుగు), or Tamil (தமிழ்) from the language dropdown at the top of this MediVoice assistant panel. You can also adjust speech speed and mute audio in the 'Settings' page.",
            "hi-IN": "भाषा बदलने के लिए: MediVoice पैनल के शीर्ष पर ड्रॉपडाउन मेनू से हिन्दी, English, తెలుగు, या தமிழ் चुनें। आप 'Settings' पेज पर आवाज़ की गति और म्यूट भी नियंत्रित कर सकते हैं।",
            "te-IN": "భాషను మార్చడానికి: ఈ MediVoice ప్యానెల్ ఎగువన ఉన్న డ్రాప్‌డౌన్ నుండి తెలుగు, English, हिन्दी, లేదా தமிழ் ఎంచుకోండి. 'Settings' పేజీలో స్పీచ్ వేగం కూడా మార్చవచ్చు.",
            "ta-IN": "மொழியை மாற்ற: MediVoice பேனலின் மேற்புறத்தில் உள்ள கீழ்தோன்றும் மெனுவிலிருந்து தமிழ், English, हिन्दी, அல்லது తెలుగు என்பதை தேர்ந்தெடுக்கவும். 'Settings' பக்கத்தில் குரல் வேகத்தையும் சரிசெய்யலாம்."
        }
        return {
            "reply": lang_replies.get(lang, lang_replies["en-IN"]),
            "action": None,
            "mode": "app_guide",
            "lang": lang,
            "authorized": True
        }

    # E. Caregiver adherence check help
    cg_help_patterns = [
        "how can my caregiver check my adherence", "caregiver features", "caregiver access", "how does caregiver see",
        "केयरगिवर कैसे देख सकता है", "देखभालकर्ता कैसे देखे",
        "కేర్‌గివర్ ఎలా చూడగలరు", "కేర్‌గివర్ ఫీచర్లు",
        "பராமரிப்பாளர் எப்படி பார்ப்பார்"
    ]
    if any(p in text for p in cg_help_patterns):
        cg_replies = {
            "en-IN": "Your authorized caregiver logs into their Caregiver Dashboard (e.g. caregiver@test.com) to view your daily adherence percentage, real-time missed dose alerts, and 7-day compliance history. They can also ask MediVoice about your status!",
            "hi-IN": "आपके अधिकृत केयरगिवर अपने डैशबोर्ड में लॉगिन करके आपकी आज की अनुपालन दर, छूटी हुई दवाओं के अलर्ट और 7-दिवसीय इतिहास देख सकते हैं।",
            "te-IN": "మీ అధీకృత కేర్‌గివర్ వారి కేర్‌గివర్ డ్యాష్‌బోర్డ్‌లోకి లాగిన్ అయి మీ రోజువారీ అడ్హీరెన్స్ శాతం, మిస్ అయిన డోస్ హెచ్చరికలు మరియు 7 రోజుల చరిత్రను చూడవచ్చు.",
            "ta-IN": "உங்கள் அங்கீகரிக்கப்பட்ட பராமரிப்பாளர் தனது டாஷ்போர்டில் உள்நுழைந்து உங்கள் தினசரி பின்பற்றும் வீதம், தவறவிட்ட மருந்து எச்சரிக்கைகள் மற்றும் வரலாற்றைக் காணலாம்."
        }
        return {
            "reply": cg_replies.get(lang, cg_replies["en-IN"]),
            "action": None,
            "mode": "app_guide",
            "lang": lang,
            "authorized": True
        }

    cursor = db_conn.cursor()

    # =========================================================================
    # 3. PATIENT DATABASE-GROUNDED INTENTS
    # =========================================================================
    if user_role == "patient":
        patient_id = user_id

        # 1. Today's Medicines
        today_med_patterns = [
            "medicines do i need to take", "medicines today", "what do i take today", "scheduled today", "today's medicine", "my medications today", "medicines do i have scheduled today",
            "आज कौन सी दवा लेनी है", "आज की दवाएं", "आज मुझे क्या लेना है",
            "ఈరోజు ఏ మందులు వేసుకోవాలి", "నేటి మందులు", "ఈరోజు షెడ్యూల్",
            "இன்று என்ன மருந்து எடுக்க வேண்டும்", "இன்றைய மருந்துகள்"
        ]
        if any(p in text for p in today_med_patterns):
            cursor.execute("""
                SELECT m.medicine_name, m.dosage, m.scheduled_time, m.instructions, COALESCE(a.status, 'PENDING') as status
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
                ORDER BY m.scheduled_time ASC
            """, (today_str, patient_id, today_str, today_str))
            meds = cursor.fetchall()

            if not meds:
                empty_replies = {
                    "en-IN": "You do not have any medications scheduled for today in your system.",
                    "hi-IN": "सिस्टम में आज के लिए आपकी कोई निर्धारित दवा नहीं है।",
                    "te-IN": "సిస్టమ్‌లో ఈరోజు కోసం మీకు ఎలాంటి మందులు షెడ్యూల్ చేయబడలేదు.",
                    "ta-IN": "இன்றைய அட்டவணையில் உங்களுக்கான மருந்துகள் எதுவும் இல்லை."
                }
                return {
                    "reply": empty_replies.get(lang, empty_replies["en-IN"]),
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }

            lines = []
            for m in meds:
                st = m["status"]
                inst = f" [{m['instructions']}]" if m["instructions"] else ""
                lines.append(f"{m['medicine_name']} ({m['dosage']}) at {m['scheduled_time']} - Status: {st}{inst}")

            joined = "; ".join(lines)
            if lang == "hi-IN":
                reply = f"आज आपके लिए {len(meds)} दवाएं निर्धारित हैं: {joined}।"
            elif lang == "te-IN":
                reply = f"ఈరోజు మీకు {len(meds)} మందులు షెడ్యూల్ చేయబడ్డాయి: {joined}."
            elif lang == "ta-IN":
                reply = f"இன்று உங்களுக்கு {len(meds)} மருந்துகள் திட்டமிடப்பட்டுள்ளன: {joined}."
            else:
                reply = f"Today you have {len(meds)} scheduled medicine{'s' if len(meds) > 1 else ''}: {joined}."

            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # 2. Missed Doses
        missed_patterns = [
            "missed any doses", "missed dose", "have i missed", "any missed", "missed medicines",
            "कोई दवा छूटी है", "क्या मेरी दवा छूटी", "छूटी हुई दवाएं",
            "ఏవైనా మందులు మిస్ అయ్యాయా", "మిస్ అయిన డోసులు",
            "மருந்தை தவறவிட்டேனா", "தவறவிட்ட மருந்துகள்"
        ]
        if any(p in text for p in missed_patterns):
            week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT a.scheduled_date, a.scheduled_time, m.medicine_name, m.dosage
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ? AND a.scheduled_date >= ? AND a.status = 'MISSED'
                ORDER BY a.scheduled_date DESC
            """, (patient_id, week_ago))
            missed = cursor.fetchall()

            if not missed:
                no_miss_replies = {
                    "en-IN": "Great job! You have not missed any medication doses in the past seven days.",
                    "hi-IN": "बहुत बढ़िया! पिछले सात दिनों में आपकी कोई भी दवा नहीं छूटी है।",
                    "te-IN": "చాలా బాగుంది! గత ఏడు రోజుల్లో మీరు ఎలాంటి మందుల డోస్ మిస్ కాలేదు.",
                    "ta-IN": "மிக நன்று! கடந்த ஏழு நாட்களில் நீங்கள் எந்த மருந்தையும் தவறவிடவில்லை."
                }
                return {
                    "reply": no_miss_replies.get(lang, no_miss_replies["en-IN"]),
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }

            desc = [f"{m['medicine_name']} ({m['dosage']}) on {m['scheduled_date']} at {m['scheduled_time']}" for m in missed]
            joined = ", ".join(desc)
            if lang == "hi-IN":
                reply = f"इस सप्ताह आपकी {len(missed)} छूटी हुई खुराकें दर्ज हैं: {joined}। कृपया समय पर दवा लें।"
            elif lang == "te-IN":
                reply = f"ఈ వారం మీరు {len(missed)} డోసులు మిస్ అయ్యారు: {joined}. దయచేసి సమయానికి మందులు వేసుకోండి."
            elif lang == "ta-IN":
                reply = f"இந்த வாரம் நீங்கள் {len(missed)} மருந்துகளை தவறவிட்டுள்ளீர்கள்: {joined}."
            else:
                reply = f"You have {len(missed)} missed dose{'s' if len(missed) > 1 else ''} recorded this week: {joined}. Remember to stay consistent with your schedule."

            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # 3. Adherence Percentage
        adh_patterns = [
            "adherence percentage", "adherence rate", "my adherence", "compliance rate",
            "अनुपालन प्रतिशत", "मेरा adherence क्या है",
            "అడ్హీరెన్స్ శాతం", "నా అడ్హీరెన్స్ ఎంత",
            "பின்பற்றும் வீதம்", "எனது adherence சதவீதம்"
        ]
        if any(p in text for p in adh_patterns):
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as taken_count
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ?
            """, (patient_id,))
            row = cursor.fetchone()
            total = row["total"] or 0
            taken = row["taken_count"] or 0
            pct = round((taken / total * 100), 1) if total > 0 else 0

            if lang == "hi-IN":
                reply = f"आपकी कुल दवा अनुपालन दर (Adherence Rate) {pct}% है, जिसमें कुल {total} निर्धारित खुराकों में से {taken} ली गई हैं।"
            elif lang == "te-IN":
                reply = f"మీ మొత్తం మందుల అడ్హీరెన్స్ రేటు {pct}%. మొత్తం {total} షెడ్యూల్ చేసిన డోసులలో {taken} డోసులు విజయవంతంగా తీసుకున్నారు."
            elif lang == "ta-IN":
                reply = f"உங்கள் ஒட்டுமொத்த மருந்து பின்பற்றும் வீதம் {pct}%. மொத்தம் {total} மருந்துகளில் {taken} மருந்துகள் எடுக்கப்பட்டுள்ளன."
            else:
                reply = f"Your overall medication adherence rate is {pct}%, with {taken} doses confirmed taken out of {total} total scheduled doses."

            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # 4. Medication History
        hist_patterns = [
            "medication history", "adherence history", "show my history", "history log",
            "दवा का इतिहास", "हिस्ट्री दिखाएं",
            "మందుల చరిత్ర", "హిస్టరీ చూపించు",
            "மருந்து வரலாறு", "வரலாற்றைக் காட்டு"
        ]
        if any(p in text for p in hist_patterns):
            hist_replies = {
                "en-IN": "Opening your complete medication adherence history log...",
                "hi-IN": "आपका पूरा दवा इतिहास (Adherence History) खोला जा रहा है...",
                "te-IN": "మీ పూర్తి మందుల అడ్హీరెన్స్ హిస్టరీ తెరవబడుతోంది...",
                "ta-IN": "உங்கள் முழுமையான மருந்து வரலாறு திறக்கப்படுகிறது..."
            }
            return {
                "reply": hist_replies.get(lang, hist_replies["en-IN"]),
                "action": {"type": "navigate", "url": "/history"},
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # 5. Next Scheduled Dose
        next_patterns = [
            "next scheduled medicine", "next medicine", "next dose", "when is my next",
            "अगली दवा कब है", "अगली दवा",
            "తదుపరి మందు ఎప్పుడు", "తర్వాత డోస్ ఎప్పుడు",
            "அடுத்த மருந்து எப்போது"
        ]
        if any(p in text for p in next_patterns):
            cursor.execute("""
                SELECT m.medicine_name, m.dosage, m.scheduled_time, COALESCE(a.status, 'PENDING') as status
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
                  AND (a.status IS NULL OR a.status = 'PENDING')
                ORDER BY m.scheduled_time ASC
                LIMIT 1
            """, (today_str, patient_id, today_str, today_str))
            next_med = cursor.fetchone()

            if next_med:
                if lang == "hi-IN":
                    reply = f"आपकी अगली निर्धारित दवा {next_med['medicine_name']} ({next_med['dosage']}) है, जो {next_med['scheduled_time']} पर निर्धारित है।"
                elif lang == "te-IN":
                    reply = f"మీ తదుపరి షెడ్యూల్ చేసిన మందు {next_med['medicine_name']} ({next_med['dosage']}), సమయం: {next_med['scheduled_time']}."
                elif lang == "ta-IN":
                    reply = f"உங்கள் அடுத்த திட்டமிடப்பட்ட மருந்து {next_med['medicine_name']} ({next_med['dosage']}), நேரம்: {next_med['scheduled_time']}."
                else:
                    reply = f"Your next scheduled pending dose today is {next_med['medicine_name']} ({next_med['dosage']}) scheduled for {next_med['scheduled_time']}."
                return {
                    "reply": reply,
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }
            else:
                all_done = {
                    "en-IN": "You have no remaining pending doses scheduled for today. All doses have been confirmed!",
                    "hi-IN": "आज के लिए आपकी कोई लंबित दवा शेष नहीं है। सभी खुराकें पुष्ट हो चुकी हैं!",
                    "te-IN": "ఈరోజు కోసం మీకు పెండింగ్‌లో ఉన్న మందులు ఏవీ లేవు. అన్ని డోసులు పూర్తయ్యాయి!",
                    "ta-IN": "இன்று நிலுவையில் உள்ள மருந்துகள் எதுவும் இல்லை. அனைத்தும் முடிக்கப்பட்டுவிட்டன!"
                }
                return {
                    "reply": all_done.get(lang, all_done["en-IN"]),
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }

        # 6. Dose Confirmation Voice Trigger ("I took my medicine" / "I took Paracetamol")
        confirm_patterns = [
            "i took my medicine", "i took", "confirm taken", "mark as taken",
            "मैंने दवा ले ली", "दवा खा ली", "दवा ले ली",
            "నేను మందు తీసుకున్నాను", "మందు వేసుకున్నాను",
            "நான் மருந்து எடுத்துக்கொண்டேன்", "மருந்து சாப்பிட்டேன்"
        ]
        if any(p in text for p in confirm_patterns):
            cursor.execute("""
                SELECT m.id, m.medicine_name, m.dosage, m.scheduled_time, a.id as adherence_id, COALESCE(a.status, 'PENDING') as status
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
            """, (today_str, patient_id, today_str, today_str))
            all_today = cursor.fetchall()
            pending = [m for m in all_today if m["status"] == "PENDING"]

            matched = [m for m in pending if m["medicine_name"].lower() in text]
            target = None
            if len(matched) == 1:
                target = matched[0]
            elif len(pending) == 1:
                target = pending[0]

            if target:
                now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if target["adherence_id"]:
                    cursor.execute("UPDATE adherence SET status = 'TAKEN', confirmed_at = ? WHERE id = ?", (now_time, target["adherence_id"]))
                else:
                    cursor.execute("""
                        INSERT INTO adherence (medication_id, scheduled_date, scheduled_time, status, confirmed_at)
                        VALUES (?, ?, ?, 'TAKEN', ?)
                    """, (target["id"], today_str, target["scheduled_time"], now_time))
                db_conn.commit()

                if lang == "hi-IN":
                    reply = f"पुष्टि हो गई! मैंने {target['medicine_name']} ({target['dosage']}) को TAKEN (ली गई) के रूप में दर्ज कर दिया है।"
                elif lang == "te-IN":
                    reply = f"నిర్ధారించబడింది! నేను {target['medicine_name']} ({target['dosage']}) ను TAKEN గా నమోదు చేసాను."
                elif lang == "ta-IN":
                    reply = f"உறுதிப்படுத்தப்பட்டது! {target['medicine_name']} ({target['dosage']}) எடுக்கப்பட்டதாக (TAKEN) பதிவு செய்யப்பட்டது."
                else:
                    reply = f"Confirmed! I have recorded your scheduled dose of {target['medicine_name']} ({target['dosage']}) as TAKEN."

                return {
                    "reply": reply,
                    "action": {"type": "refresh_dashboard"},
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }
            elif len(pending) > 1:
                names = [m["medicine_name"] for m in pending]
                joined = ", ".join(names)
                if lang == "hi-IN":
                    reply = f"आज आपकी कई दवाएं लंबित हैं ({joined})। आपने कौन सी दवा ली?"
                elif lang == "te-IN":
                    reply = f"ఈరోజు మీకు అనేక మందులు పెండింగ్‌లో ఉన్నాయి ({joined}). మీరు ఏ మందు తీసుకున్నారు?"
                elif lang == "ta-IN":
                    reply = f"இன்று பல மருந்துகள் நிலுவையில் உள்ளன ({joined}). நீங்கள் எந்த மருந்தை எடுத்தீர்கள்?"
                else:
                    reply = f"You have multiple pending medications today ({joined}). Which medicine did you take?"
                return {
                    "reply": reply,
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }
            else:
                already_replies = {
                    "en-IN": "All your medications for today are already confirmed as taken or missed.",
                    "hi-IN": "आज के लिए आपकी सभी दवाएं पहले से ही पुष्ट हो चुकी हैं।",
                    "te-IN": "ఈరోజు కోసం మీ అన్ని మందులు ఇప్పటికే నిర్ధారించబడ్డాయి.",
                    "ta-IN": "இன்றைய அனைத்து மருந்துகளும் ஏற்கனவே உறுதிப்படுத்தப்பட்டுவிட்டன."
                }
                return {
                    "reply": already_replies.get(lang, already_replies["en-IN"]),
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }

        # Patient generic fallback
        fallbacks = {
            "en-IN": f"I heard: '{raw_text}'. You can ask me: 'What medicines do I take today?', 'What is my adherence percentage?', 'Have I missed any doses this week?', or 'How do I add a new medicine?'.",
            "hi-IN": f"मैंने सुना: '{raw_text}'। आप मुझसे पूछ सकते हैं: 'आज की दवाएं क्या हैं?', 'मेरा adherence क्या है?', 'क्या मेरी दवा छूटी है?', या 'नई दवा कैसे जोड़ूँ?'।",
            "te-IN": f"నేను విన్నాను: '{raw_text}'. మీరు నన్ను అడగవచ్చు: 'ఈరోజు నా మందులు ఏమిటి?', 'నా అడ్హీరెన్స్ ఎంత?', లేదా 'కొత్త మందును ఎలా జోడించాలి?'.",
            "ta-IN": f"நான் கேட்டது: '{raw_text}'. நீங்கள் என்னிடம் கேட்கலாம்: 'இன்றைய மருந்துகள் என்ன?', 'எனது adherence எவ்வளவு?', அல்லது 'புதிய மருந்தை எப்படி சேர்ப்பது?'."
        }
        return {
            "reply": fallbacks.get(lang, fallbacks["en-IN"]),
            "action": None,
            "mode": "rule_based",
            "lang": lang,
            "authorized": True
        }

    # =========================================================================
    # 4. CAREGIVER DATABASE-GROUNDED INTENTS (Authorized Access Guarded)
    # =========================================================================
    elif user_role == "caregiver":
        caregiver_id = user_id

        # Verify authorized patients for this caregiver
        cursor.execute("""
            SELECT cp.patient_id, u.name, u.email
            FROM caregiver_patients cp
            JOIN users u ON cp.patient_id = u.id
            WHERE cp.caregiver_id = ?
        """, (caregiver_id,))
        authorized_patients = cursor.fetchall()

        if not authorized_patients:
            no_patient = {
                "en-IN": "You do not currently have any assigned patients authorized in your caregiver profile.",
                "hi-IN": "आपके केयरगिवर प्रोफ़ाइल में वर्तमान में कोई अधिकृत रोगी निर्दिष्ट नहीं है।",
                "te-IN": "మీ కేర్‌గివర్ ప్రొఫైల్‌లో ప్రస్తుతం ఎలాంటి అధీకృత రోగులు లేరు.",
                "ta-IN": "உங்கள் பராமரிப்பாளர் சுயவிவரத்தில் எந்த நோயாளியும் ஒதுக்கப்படவில்லை."
            }
            return {
                "reply": no_patient.get(lang, no_patient["en-IN"]),
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # Select target patient
        patient_id = None
        patient_name = "your patient"
        if target_patient_id:
            auth_match = [p for p in authorized_patients if p["patient_id"] == int(target_patient_id)]
            if auth_match:
                patient_id = auth_match[0]["patient_id"]
                patient_name = auth_match[0]["name"]
            else:
                denied_msg = {
                    "en-IN": "Access Denied: You are not authorized to view records for this patient.",
                    "hi-IN": "पहुंच अस्वीकृत: आप इस रोगी के रिकॉर्ड देखने के लिए अधिकृत नहीं हैं।",
                    "te-IN": "యాక్సెస్ నిరాకరించబడింది: ఈ రోగి రికార్డులను వీక్షించడానికి మీకు అనుమతి లేదు.",
                    "ta-IN": "அனுமதி மறுக்கப்பட்டது: இந்த நோயாளியின் பதிவுகளைப் பார்க்க உங்களுக்கு அங்கீகாரம் இல்லை."
                }
                return {
                    "reply": denied_msg.get(lang, denied_msg["en-IN"]),
                    "action": None,
                    "mode": "security_guardrail",
                    "lang": lang,
                    "authorized": False
                }
        else:
            patient_id = authorized_patients[0]["patient_id"]
            patient_name = authorized_patients[0]["name"]

        # A. Which patients missed a dose today?
        cg_miss_patterns = [
            "which patients missed a dose", "who missed a dose", "missed a dose today", "missed today",
            "किस मरीज की दवा छूटी", "आज किसकी दवा छूटी",
            "ఏ రోగులు మందు మిస్ అయ్యారు", "ఈరోజు ఎవరు మందు వేసుకోలేదు",
            "யார் மருந்தை தவறவிட்டார்கள்"
        ]
        if any(p in text for p in cg_miss_patterns):
            auth_ids = [p["patient_id"] for p in authorized_patients]
            placeholders = ",".join("?" for _ in auth_ids)
            cursor.execute(f"""
                SELECT u.name, m.medicine_name, m.dosage, a.scheduled_time
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                JOIN users u ON m.patient_id = u.id
                WHERE m.patient_id IN ({placeholders}) AND a.scheduled_date = ? AND a.status = 'MISSED'
            """, auth_ids + [today_str])
            missed_today = cursor.fetchall()

            if not missed_today:
                none_msg = {
                    "en-IN": "None of your assigned patients have missed any doses today. All checked prescriptions are on schedule.",
                    "hi-IN": "आपके किसी भी मरीज की आज कोई दवा नहीं छूटी है। सभी दवाएं समय पर हैं।",
                    "te-IN": "మీ రోగులలో ఎవరూ ఈరోజు మందులను మిస్ కాలేదు. అన్నీ సక్రమంగా ఉన్నాయి.",
                    "ta-IN": "உங்கள் நோயாளிகள் யாரும் இன்று மருந்தை தவறவிடவில்லை."
                }
                return {
                    "reply": none_msg.get(lang, none_msg["en-IN"]),
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }

            desc = [f"{r['name']} missed {r['medicine_name']} ({r['dosage']}) at {r['scheduled_time']}" for r in missed_today]
            joined = "; ".join(desc)
            if lang == "hi-IN":
                reply = f"आज निम्नलिखित छूटी हुई खुराकें दर्ज की गईं: {joined}।"
            elif lang == "te-IN":
                reply = f"ఈరోజు గుర్తించబడిన మిస్ అయిన డోసులు: {joined}."
            elif lang == "ta-IN":
                reply = f"இன்று தவறவிடப்பட்ட மருந்துகள்: {joined}."
            else:
                reply = f"Today, the following missed doses were detected: {joined}."

            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # B. Show this patient's adherence for the last seven days
        cg_adh_patterns = [
            "adherence for the last seven days", "seven days adherence", "7 days adherence", "weekly adherence",
            "पिछले सात दिनों का adherence", "साप्ताहिक अनुपालन",
            "గత ఏడు రోజుల అడ్హీరెన్స్", "వారం రోజుల అడ్హీరెన్స్",
            "கடந்த ஏழு நாட்களின் பின்பற்றும் வீதம்"
        ]
        if any(p in text for p in cg_adh_patterns):
            week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN a.status = 'TAKEN' THEN 1 ELSE 0 END) as taken_count,
                    SUM(CASE WHEN a.status = 'MISSED' THEN 1 ELSE 0 END) as missed_count
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ? AND a.scheduled_date >= ?
            """, (patient_id, week_ago))
            stats = cursor.fetchone()
            total = stats["total"] or 0
            taken = stats["taken_count"] or 0
            missed = stats["missed_count"] or 0
            pct = round((taken / total * 100), 1) if total > 0 else 0

            if lang == "hi-IN":
                reply = f"मरीज {patient_name} के पिछले सात दिनों ({week_ago} से {today_str}) का adherence {pct}% है: {taken} ली गई, {missed} छूटी, कुल {total} निर्धारित खुराकें।"
            elif lang == "te-IN":
                reply = f"రోగి {patient_name} కోసం గత ఏడు రోజుల ({week_ago} నుండి {today_str}) అడ్హీరెన్స్ {pct}%: {taken} తీసుకున్నారు, {missed} మిస్ అయ్యారు, మొత్తం {total} డోసులు."
            elif lang == "ta-IN":
                reply = f"நோயாளி {patient_name} இன் கடந்த 7 நாட்களின் ({week_ago} முதல் {today_str}) adherence {pct}%: {taken} எடுக்கப்பட்டது, {missed} தவறவிடப்பட்டது, மொத்தம் {total} மருந்துகள்."
            else:
                reply = f"For {patient_name} over the last seven days ({week_ago} to {today_str}), adherence is {pct}%, with {taken} taken doses, {missed} missed doses, out of {total} scheduled doses."

            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # C. Pending scheduled doses
        cg_pend_patterns = [
            "pending scheduled doses", "pending doses", "what is pending", "medicines pending",
            "कौन सी दवाएं लंबित हैं", "पेंडिंग दवाएं",
            "పెండింగ్ డోసులు", "ఏ మందులు పెండింగ్‌లో ఉన్నాయి",
            "நிலுவையில் உள்ள மருந்துகள்"
        ]
        if any(p in text for p in cg_pend_patterns):
            cursor.execute("""
                SELECT m.medicine_name, m.dosage, m.scheduled_time
                FROM medications m
                LEFT JOIN adherence a ON m.id = a.medication_id AND a.scheduled_date = ?
                WHERE m.patient_id = ? AND m.start_date <= ? AND m.end_date >= ?
                  AND (a.status IS NULL OR a.status = 'PENDING')
                ORDER BY m.scheduled_time ASC
            """, (today_str, patient_id, today_str, today_str))
            pending_meds = cursor.fetchall()

            if not pending_meds:
                no_pend = {
                    "en-IN": f"{patient_name} has no pending scheduled doses remaining for today.",
                    "hi-IN": f"{patient_name} की आज कोई लंबित दवा शेष नहीं है।",
                    "te-IN": f"{patient_name} కు ఈరోజు ఎలాంటి పెండింగ్ మందులు లేవు.",
                    "ta-IN": f"{patient_name} க்கு இன்று நிலுவையில் உள்ள மருந்துகள் இல்லை."
                }
                return {
                    "reply": no_pend.get(lang, no_pend["en-IN"]),
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }

            desc = [f"{p['medicine_name']} ({p['dosage']}) at {p['scheduled_time']}" for p in pending_meds]
            joined = ", ".join(desc)
            if lang == "hi-IN":
                reply = f"{patient_name} की आज {len(pending_meds)} लंबित खुराकें हैं: {joined}।"
            elif lang == "te-IN":
                reply = f"{patient_name} కు ఈరోజు {len(pending_meds)} పెండింగ్ డోసులు ఉన్నాయి: {joined}."
            elif lang == "ta-IN":
                reply = f"{patient_name} க்கு இன்று {len(pending_meds)} நிலுவையில் உள்ள மருந்துகள் உள்ளன: {joined}."
            else:
                reply = f"{patient_name} currently has {len(pending_meds)} pending dose{'s' if len(pending_meds) > 1 else ''} today: {joined}."

            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # D. Summarize recent missed doses
        cg_sum_patterns = [
            "recent missed doses", "summarize missed doses", "missed dose summary",
            "छूटी दवाओं का सारांश",
            "మిస్ అయిన డోసుల సారాంశం",
            "தவறவிட்ட மருந்துகளின் சுருக்கம்"
        ]
        if any(p in text for p in cg_sum_patterns):
            cursor.execute("""
                SELECT a.scheduled_date, a.scheduled_time, m.medicine_name, m.dosage
                FROM adherence a
                JOIN medications m ON a.medication_id = m.id
                WHERE m.patient_id = ? AND a.status = 'MISSED'
                ORDER BY a.scheduled_date DESC, a.scheduled_time DESC
                LIMIT 5
            """, (patient_id,))
            recent_missed = cursor.fetchall()

            if not recent_missed:
                clean_msg = {
                    "en-IN": f"{patient_name} has no recent missed doses logged.",
                    "hi-IN": f"{patient_name} की कोई हालिया छूटी हुई दवा दर्ज नहीं है।",
                    "te-IN": f"{patient_name} కు సంబంధించి ఎలాంటి మిస్ అయిన డోసులు నమోదు కాలేదు.",
                    "ta-IN": f"{patient_name} க்கு அண்மையில் தவறவிட்ட மருந்துகள் எதுவும் இல்லை."
                }
                return {
                    "reply": clean_msg.get(lang, clean_msg["en-IN"]),
                    "action": None,
                    "mode": "rule_based",
                    "lang": lang,
                    "authorized": True
                }

            desc = [f"{m['medicine_name']} on {m['scheduled_date']} ({m['scheduled_time']})" for m in recent_missed]
            joined = ", ".join(desc)
            if lang == "hi-IN":
                reply = f"{patient_name} के लिए हालिया छूटी हुई खुराकें: {joined}।"
            elif lang == "te-IN":
                reply = f"{patient_name} కొరకు ఇటీవల మిస్ అయిన డోసులు: {joined}."
            elif lang == "ta-IN":
                reply = f"{patient_name} தவறவிட்ட சமீபத்திய மருந்துகள்: {joined}."
            else:
                reply = f"Recent missed doses for {patient_name}: {joined}."

            return {
                "reply": reply,
                "action": None,
                "mode": "rule_based",
                "lang": lang,
                "authorized": True
            }

        # Caregiver generic fallback
        cg_fallbacks = {
            "en-IN": f"As caregiver for {patient_name}, you can ask: 'Which patients missed a dose today?', 'Show this patient\'s adherence for the last seven days', or 'Which medicines have pending scheduled doses?'.",
            "hi-IN": f"{patient_name} के केयरगिवर के रूप में आप पूछ सकते हैं: 'आज किसकी दवा छूटी?', 'साप्ताहिक adherence दिखाएं', या 'कौन सी दवाएं लंबित हैं?'।",
            "te-IN": f"{patient_name} కేర్‌గివర్‌గా మీరు అడగవచ్చు: 'ఈరోజు ఎవరు మందు మిస్ అయ్యారు?', 'గత 7 రోజుల అడ్హీరెన్స్ చూపించు', లేదా 'ఏ మందులు పెండింగ్‌లో ఉన్నాయి?'.",
            "ta-IN": f"{patient_name} பராமரிப்பாளராக நீங்கள் கேட்கலாம்: 'இன்று யார் மருந்தை தவறவிட்டார்கள்?', 'கடந்த 7 நாட்களின் adherence காட்டு', அல்லது 'எந்த மருந்துகள் நிலுவையில் உள்ளன?'."
        }
        return {
            "reply": cg_fallbacks.get(lang, cg_fallbacks["en-IN"]),
            "action": None,
            "mode": "rule_based",
            "lang": lang,
            "authorized": True
        }

    return {
        "reply": "Role unrecognized.",
        "action": None,
        "mode": "rule_based",
        "lang": lang,
        "authorized": False
    }
