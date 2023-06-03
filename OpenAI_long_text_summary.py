import os
import openai
import time
import re
import PyPDF2

OPENAI_API_KEY = 'Your OpenAI Key'
openai.api_key = OPENAI_API_KEY

def detect_main_language(text):
    english_count = len(re.findall('[a-zA-Z]', text))
    chinese_count = len(re.findall('[\u4e00-\u9fa5]', text))
    japanese_count = len(re.findall('[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]', text))

    max_count = max(english_count, chinese_count, japanese_count)
    # print(english_count, chinese_count, japanese_count)

    if max_count == english_count:
        return 'English'
    elif max_count == chinese_count:
        return '中文'
    elif max_count == japanese_count:
        return '日本語'
    else:
        return 'English'

def get_prompt(language, contexts, chunk, summary_length_per_chunk):
    if language == 'English':
        return f'{contexts[-1]}"""{chunk}"""\nPlease condense the above into {summary_length_per_chunk} key points using "{language}":\nFormat: \n1. ...\n2. ...\n3. ...\nThe last point should be a summary of this paragraph, starting with "0. Summary of this paragraph: "'
    elif language == '中文':
        return f'{contexts[-1]}"""{chunk}"""\n请用"{language}"将以上内容总结成{summary_length_per_chunk}个要点，格式如下:\n1. ...\n2. ...\n3. ...\n最后一点应是这段的总结，以 "0. 这段的总结："为开头'
    elif language == '日本語':
        return f'{contexts[-1]}"""{chunk}"""\n以上の内容を"{language}"で{summary_length_per_chunk}の要点にまとめてください。形式:\n1. ...\n2. ...\n3. ...\n最後のポイントはこの段落の要約で、"0. この段落の要約："で始めてください。'
    else:
        return f'{contexts[-1]}"""{chunk}"""\nPlease condense the above into {summary_length_per_chunk} key points using "{language}":\nFormat: \n1. ...\n2. ...\n3. ...\nThe last point should be a summary of this paragraph, starting with "0. Summary of this paragraph: "'

def update_context(result, language):
    previous_context = result.split('\n')[-1].split('0. ')[-1]
    if language == 'English':
        if previous_context.find('Summary of this paragraph:')==-1:
            previous_context = 'Summary of this paragraph:' + previous_context
        new_context = previous_context.replace('Summary of this paragraph','Summary of the previous paragraph')+'\nThis paragraph content:\n'
    elif language == '中文':
        if previous_context.find('本段的总结：')==-1:
            previous_context = '本段的总结：' + previous_context
        new_context = previous_context.replace('本段的总结：','前一段的总结：')+'\n本段内容：\n'
    elif language == '日本語':
        if previous_context.find('この段落の要約：')==-1:
            previous_context = 'この段落の要約：' + previous_context
        new_context = previous_context.replace('この段落の要約：','前の段落の要約：')+'\nこの段落の内容：\n'
    else:
        if previous_context.find('Summary of this paragraph:')==-1:
            previous_context = 'Summary of this paragraph:' + previous_context
        new_context = previous_context.replace('Summary of this paragraph','Summary of the previous paragraph')+'\nThis paragraph content:\n'
    return new_context

def extract_text_from_pdf(file_path):
    with open(file_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        num_pages = len(pdf_reader.pages)
        text = ''
        for page_number in range(num_pages):
            page = pdf_reader.pages[page_number]
            text += page.extract_text()
        # Ignore REFERENCES
        temp = text.lower().split('\nreferences')[0]
        length_without_references = len(temp)
        text = text[:length_without_references]
        return text

def chunk_text(text, chunk_size=1800, overlap=50):
    chunks = []
    start = 0
    end = chunk_size
    while start < len(text):
        if end < len(text):
            chunks.append(text[start:end])
            start = end - overlap
            end = start + chunk_size
        else:
            if len(text[start:]) < 200 and len(chunks) > 0: # Combine if too short
                chunks[-1] += text[start:]
            else:
                chunks.append(text[start:])
            break
    return chunks

def summarize_text(text, overlap=10, total_summary_length=80, model="gpt-3.5-turbo"): #  -> str
    language = detect_main_language(text)
    chunks = chunk_text(text, 1800, overlap)
    summary_length_per_chunk = max(min(total_summary_length // len(chunks), 10), 3)

    summaries = []
    contexts = ['']
    for i,chunk in enumerate(chunks):
        prompt = get_prompt(language, contexts, chunk, summary_length_per_chunk)         
        response = openai.ChatCompletion.create(
            model = model,
            messages=[
                      {"role": "user", 
                       "content": prompt}
            ]
        )
        result = response.choices[0]["message"]['content']
        contexts.append(update_context(result, language))       # context
        summaries.append('\n'.join(result.split('\n')[:-1]))    # summaries
        time.sleep(2)
        print("summaries:\n",'\n'.join(result.split('\n')[:-1]))
        print("context:\n",update_context(result, language))
    # Combine summaries into a str
    summaries = "\n".join(summaries).replace('\n\n','\n')
    summaries = '\n'.join([str(i+1)+'. '+x.strip(' ').split('. ')[-1] for i,x in enumerate(summaries.split('\n')) if x])
    return summaries

def save_summaries_to_file(summaries, filename):
    with open(filename, "w", encoding="utf-8-sig") as file:
        file.write(summaries)

def create_article_from_summaries(summaries, model="gpt-4"):
    language = detect_main_language(summaries)
    prompt = f"Here is a summary of the key points from a video:\n'''{summaries}'''\nBased on the information provided, please write an article in '{language}', starting with the title:"
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{
                "role": "user", 
                "content": prompt
            }]
        )
        result = response.choices[0]["message"]['content']
        return result
    except Exception as e:
        return str(e)

def main():
    file_path = input("Please input .txt、.pdf file：").strip("'").strip('"').replace("'","\'").replace('"', '\"')
    file_path = os.path.normpath(file_path) 
    with open(file_path, "r", encoding='utf-8-sig') as f:
        if os.path.splitext(file_path)[1] == '.pdf':
            text = extract_text_from_pdf(file_path)
        else:
            text = f.read()
    # Check if text is shorter than 1500
    chunk_lst = chunk_text(text, 1500)
    
    # Generate summaries
    path,filename_ext = os.path.split(file_path)
    filename = os.path.splitext(filename_ext)[0]
    if len(chunk_lst[0]) >= 1500:
        summaries = summarize_text(text, model="gpt-3.5-turbo")
        # key_point = len(summaries.split('\n'))
        # print(key_point)
        save_summaries_to_file(summaries, os.path.join(path,filename+"_[summaries].txt"))  
        article = create_article_from_summaries(summaries, model="gpt-3.5-turbo") # model="gpt-4" model="gpt-3.5-turbo"
    else:
        article = create_article_from_summaries(chunk_lst[0], model="gpt-3.5-turbo") # model="gpt-4" model="gpt-3.5-turbo"
    # save
    with open(os.path.join(path,filename+"_[article].txt"), "w", encoding='utf-8-sig') as file:
        file.write(article)

if __name__ == "__main__":
    main()
