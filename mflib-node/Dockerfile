FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY mflib_node ./mflib_node

ENV PYTHONUNBUFFERED=1

EXPOSE 5000

ENTRYPOINT ["python", "-m", "mflib_node.server"]
CMD ["--port", "5000"]
