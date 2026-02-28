import os
import re
from collections import defaultdict

def preprocess_daily_dump(work_dir):
    inbox_path = os.path.join(work_dir, "00_inbox")
    dump_file = os.path.join(inbox_path, "daily_dump.md")
    output_file = os.path.join(inbox_path, "daily_preprocessed.md")

    if not os.path.exists(dump_file):
        print(f"Error: {dump_file} not found.")
        return

    with open(dump_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 按一级标题拆分内容
    # 正则匹配 # Title ... 直到下一个 # 或结尾
    sections = re.split(r'\n(?=# )', "\n" + content)
    
    merged_data = defaultdict(list)
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
        
        lines = section.split('\n')
        title = lines[0].lstrip('#').strip()
        body = '\n'.join(lines[1:]).strip()
        
        if body:
            merged_data[title].append(body)

    # 写入预处理文件
    with open(output_file, "w", encoding="utf-8") as f:
        for title, bodies in merged_data.items():
            f.write(f"# {title}\n\n")
            # 同一标题下的内容直接合并
            combined_body = "\n\n---\n\n".join(bodies)
            f.write(combined_body)
            f.write("\n\n")

    print(f"Success: Merged {len(merged_data)} sections into {output_file}")

if __name__ == "__main__":
    # 从环境变量或硬编码获取工作目录
    work_dir = "/Users/xiongmengjun/Documents/工作助手"
    preprocess_daily_dump(work_dir)
