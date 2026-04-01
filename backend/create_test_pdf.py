from fpdf import FPDF

pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", size=12)

questions = [
    "1. Do you encrypt data at rest?",
    "2. Do you encrypt data in transit?",
    "3. Do you have a data backup policy?",
    "4. Do you conduct regular security audits?",
    "5. Do you have an incident response plan?",
    "6. Do you use multi-factor authentication?",
    "7. How do you manage access control?",
    "8. Do you have a vulnerability management program?",
    "9. Do you conduct employee security training?",
    "10. Do you have a business continuity plan?",
]

pdf.cell(200, 10, text="SOC 2 Security Questionnaire", ln=True, align="C")
pdf.ln(10)
for q in questions:
    pdf.multi_cell(0, 10, text=q)
    pdf.ln(3)

pdf.output("test_questionnaire.pdf")
print("Created test_questionnaire.pdf successfully!")
