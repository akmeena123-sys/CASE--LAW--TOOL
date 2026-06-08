from flask import Flask, render_template, request, jsonify
import re
import os

app = Flask(__name__)
app.secret_key = "caselawsecretkey2024"


def get_case_laws(issue, api_key):
    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        prompt = f"""You are an expert Indian Income Tax lawyer. A tax professional needs case laws on this income tax issue:

ISSUE: {issue}

Respond ONLY in the exact format below. No bold (**), no numbering (1.), no bullet points (-).
Each field must start at the beginning of a new line exactly as shown.

==SUPREME COURT CASES==

Case Name: [Full case name e.g. CIT v. ABC Ltd.]
Citation: [Full citation e.g. (2015) 370 ITR 200 (SC)]
Court: Supreme Court of India
Year: [e.g. 2015]
Favour: [Write exactly "Revenue" if the judgment favours the Income Tax Department/Revenue, or "Assessee" if it favours the taxpayer/assessee]
Key Ruling: [2-3 sentences explaining what was decided and why it is relevant]

Case Name: [next case]
Citation: [citation]
Court: Supreme Court of India
Year: [year]
Favour: [Revenue or Assessee]
Key Ruling: [ruling]

==HIGH COURT CASES==

Case Name: [Full case name]
Citation: [Full citation]
Court: [Specific High Court e.g. Delhi High Court, Bombay High Court, Madras High Court]
Year: [year]
Favour: [Revenue or Assessee]
Key Ruling: [ruling]

==ITAT CASES==

Case Name: [Full case name]
Citation: [Full citation]
Court: [Specific ITAT bench e.g. ITAT Delhi, ITAT Mumbai, ITAT Chennai]
Year: [year]
Favour: [Revenue or Assessee]
Key Ruling: [ruling]

Rules:
- Provide as many cases as possible — aim for at least 8 to 10 cases per section (Supreme Court, High Court, ITAT)
- Include a good mix: roughly half Revenue and half Assessee favour in each section
- For High Court cases: include cases from as many different High Courts (states) as possible
- For ITAT cases: include cases from as many different ITAT benches (states) as possible
- Only cite real cases that actually exist in Indian tax law
- Do not use bold (**), numbering (1.), or bullet points (-)
- Each field label must start at the beginning of the line
- Favour field must be exactly the word "Revenue" or "Assessee" only"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert Indian Income Tax lawyer. Output only the exact format requested. Never use markdown. Always include the Favour field as exactly 'Revenue' or 'Assessee'."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            max_tokens=8000
        )

        raw_text = response.choices[0].message.content
        return parse_cases(raw_text)

    except Exception as e:
        return {"error": str(e)}


def clean_field(value):
    value = re.sub(r'\*\*([^*]*)\*\*', r'\1', value)
    value = re.sub(r'^\s*[-*•]\s*', '', value)
    value = re.sub(r'^\s*\d+\.\s*', '', value)
    return value.strip()


def parse_cases(text):
    result = {
        "supreme_court": [],
        "high_court": [],
        "itat": [],
        "raw": text
    }

    # Remove markdown bold
    text = re.sub(r'\*\*([^*]*)\*\*', r'\1', text)

    current_section = None
    current_case = {}
    last_field = None

    field_pattern = re.compile(
        r'^(?:[-*•\d.]*\s*)?(Case Name|Citation|Court|Year|Favour|Key Ruling)\s*:\s*(.*)',
        re.IGNORECASE
    )

    section_patterns = {
        "supreme_court": re.compile(r'SUPREME COURT CASES', re.IGNORECASE),
        "high_court":    re.compile(r'HIGH COURT CASES', re.IGNORECASE),
        "itat":          re.compile(r'ITAT CASES', re.IGNORECASE),
    }

    lines = text.split("\n")

    for line in lines:
        stripped = line.strip()

        # Detect section headers
        section_found = False
        for sec_key, pattern in section_patterns.items():
            if pattern.search(stripped):
                if current_case and "name" in current_case and current_section:
                    result[current_section].append(current_case)
                    current_case = {}
                current_section = sec_key
                last_field = None
                section_found = True
                break
        if section_found:
            continue

        if not current_section:
            continue

        m = field_pattern.match(stripped)
        if m:
            field_key = m.group(1).strip().lower().replace(" ", "_")
            field_val = clean_field(m.group(2))

            if field_key == "case_name":
                if current_case and "name" in current_case:
                    result[current_section].append(current_case)
                    current_case = {}
                current_case["name"] = field_val
                last_field = "name"

            elif field_key == "citation":
                current_case["citation"] = field_val
                last_field = "citation"

            elif field_key == "court":
                current_case["court"] = field_val
                last_field = "court"

            elif field_key == "year":
                current_case["year"] = field_val
                last_field = "year"

            elif field_key == "favour":
                val = field_val.lower()
                if "revenue" in val or "department" in val:
                    current_case["favour"] = "Revenue"
                else:
                    current_case["favour"] = "Assessee"
                last_field = "favour"

            elif field_key == "key_ruling":
                current_case["ruling"] = field_val
                last_field = "ruling"
        else:
            # Continuation of multi-line ruling
            if last_field == "ruling" and stripped and not stripped.startswith("=="):
                current_case["ruling"] = current_case.get("ruling", "") + " " + stripped

    # Save last case
    if current_case and "name" in current_case and current_section:
        result[current_section].append(current_case)

    # Filter empty cases and set default favour if missing
    for key in ["supreme_court", "high_court", "itat"]:
        cleaned = []
        for c in result[key]:
            if c.get("name", "").strip():
                if "favour" not in c:
                    c["favour"] = "Assessee"
                cleaned.append(c)
        result[key] = cleaned

    return result


def validate_api_key(api_key):
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5
        )
        return True, "API key is valid!"
    except Exception as e:
        err = str(e)
        if "401" in err or "invalid" in err.lower() or "authentication" in err.lower():
            return False, "Invalid API key. Please check and try again."
        return False, f"Error: {err}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/validate_key", methods=["POST"])
def validate_key():
    data = request.get_json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"valid": False, "message": "Please enter an API key."})
    valid, message = validate_api_key(api_key)
    return jsonify({"valid": valid, "message": message})


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    issue = data.get("issue", "").strip()
    api_key = data.get("api_key", "").strip()

    if not issue:
        return jsonify({"error": "Please describe the income tax issue."})
    if not api_key:
        return jsonify({"error": "Please enter and validate your Groq API key first."})

    result = get_case_laws(issue, api_key)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("\n" + "="*60)
    print("  Income Tax Case Law Finder")
    print(f"  Open your browser and go to: http://127.0.0.1:{port}")
    print("  Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    app.run(debug=False, host="0.0.0.0", port=port)
