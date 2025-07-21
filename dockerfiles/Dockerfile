FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install poetry && poetry install

EXPOSE 8000

CMD ["poetry", "run", "octopus_service"]