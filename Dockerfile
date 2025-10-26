# syntax=docker/dockerfile:1
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    texlive-xetex \
    texlive-fonts-recommended \
    pandoc \
    unzip \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt ./
RUN pip3 install  -r requirements.txt

# Download and install pdf.js CMAP files for streamlit-pdf-viewer
RUN curl -L https://github.com/mozilla/pdfjs-dist/archive/master.zip -o pdfjs.zip && \
    unzip pdfjs.zip && \
    mkdir -p /usr/local/lib/python3.13/site-packages/streamlit_pdf_viewer/frontend/dist/pdfjs-dist/cmaps && \
    cp -r pdfjs-dist-master/cmaps/* /usr/local/lib/python3.13/site-packages/streamlit_pdf_viewer/frontend/dist/pdfjs-dist/cmaps/ && \
    rm -rf pdfjs.zip pdfjs-dist-master

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app/🖎_Korrektur.py", "--server.port=8501", "--server.address=0.0.0.0"]
