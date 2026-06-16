# Use a lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install the required chess library
RUN pip install --no-cache-dir chess

# Copy our new 3-tier architecture into the container
COPY server.py database.py index.html ./

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application
CMD ["python", "server.py"]