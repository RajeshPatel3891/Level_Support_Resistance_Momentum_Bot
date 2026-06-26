FROM python:3.11-slim

# Set system time to Eastern Time for the Volatility Damper
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install dependencies first to leverage Docker cache layers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Run the Scalper Sentry
CMD ["python", "-u", "src/LiveBot.py"]
