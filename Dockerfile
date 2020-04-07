FROM python:3.8-slim

# Install python package requirements
RUN pip install --no-cache-dir -r requirements.txt --upgrade

# Set working directory
WORKDIR /usr/src/app

# Add flask server files
COPY . /usr/src/app/

# Set entrypoint.sh permissions
RUN chmod +x /usr/src/app/entrypoint.sh

# Run server
CMD ["/usr/src/app/entrypoint.sh"]
