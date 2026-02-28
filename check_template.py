import re

with open(r"c:\Users\Ashish\Downloads\rubberplantation\templates\dashboard_manager.html", 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
for i, line in enumerate(lines):
    tags = re.findall(r'\{%\s*(if|elif|else|endif|for|empty|endfor|block|endblock)\b[^%]*%\}', line)
    for tag in tags:
        tag = tag.strip()
        if tag in ('if', 'for', 'block'):
            stack.append((tag, i + 1))
        elif tag == 'endif':
            if stack and stack[-1][0] == 'if':
                stack.pop()
            else:
                print(f"Error at line {i+1}: unmatched endif. Stack: {stack}")
        elif tag == 'endfor':
            if stack and stack[-1][0] == 'for':
                stack.pop()
            else:
                print(f"Error at line {i+1}: unmatched endfor. Stack: {stack}")
        elif tag == 'endblock':
            if stack and stack[-1][0] == 'block':
                stack.pop()
            else:
                print(f"Error at line {i+1}: unmatched endblock. Stack: {stack}")

if stack:
    print(f"Unmatched tags remaining in stack: {stack}")
else:
    print("All tags matched!")
