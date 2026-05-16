import zipfile
import xml.etree.ElementTree as ET

def extract_text_from_docx(docx_path):
    document = zipfile.ZipFile(docx_path)
    xml_content = document.read('word/document.xml')
    document.close()
    tree = ET.XML(xml_content)
    WORD_NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    PARA = WORD_NAMESPACE + 'p'
    TEXT = WORD_NAMESPACE + 't'
    paragraphs = []
    for paragraph in tree.iter(PARA):
        texts = [node.text
                 for node in paragraph.iter(TEXT)
                 if node.text]
        if texts:
            paragraphs.append(''.join(texts))
    return '\n'.join(paragraphs)

try:
    text = extract_text_from_docx(r"c:\Users\siddh\Desktop\boiler\PHYSICS_MODEL\BoilerTwin.docx")
    with open(r"c:\Users\siddh\Desktop\boiler\PHYSICS_MODEL\doc_text.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("Extracted successfully to doc_text.txt")
except Exception as e:
    print(f"Error: {e}")
