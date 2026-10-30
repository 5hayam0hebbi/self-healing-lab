FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
# Ansible runs against this container itself (localhost), with no inventory file
ENV ANSIBLE_LOCALHOST_WARNING=False \
    ANSIBLE_INVENTORY_UNPARSED_WARNING=False
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
