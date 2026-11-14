FROM python:3.11-slim

WORKDIR /app
COPY gigsim/requirements.txt /app/gigsim/requirements.txt
RUN pip install --no-cache-dir -r /app/gigsim/requirements.txt

COPY gigsim /app/gigsim
RUN rm -rf /app/gigsim/data /app/gigsim/tests

EXPOSE 8081
CMD ["uvicorn", "gigsim.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8081"]
