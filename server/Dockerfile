FROM python:3.13-slim

WORKDIR /app

# WeasyPrint runtime dependencies (Pango/GdkPixbuf/libffi) plus the ATS-safe
# fonts the resume template targets ('Liberation Sans', 'DejaVu Sans'). These
# are small apt packages (tens of MB) — far lighter and faster to build than
# the previous Playwright+Chromium install (several hundred MB).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libharfbuzz-subset0 \
      libgdk-pixbuf-2.0-0 \
      libffi8 \
      fonts-liberation \
      fonts-dejavu-core \
      fontconfig \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
