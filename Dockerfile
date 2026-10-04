# Imagen base de Python (slim para empezar con una imagen chica)
FROM python:3.12-slim

# Instalar herramientas y librerias de desarrollo
# meson y ninja-build sirven para compilar libvmaf
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    git \
    nasm \
    yasm \
    meson \
    ninja-build \
    xxd \
    && rm -rf /var/lib/apt/lists/*

# Instalar libvmaf v3.2.0 desde el repositorio oficial en GitHub
RUN git clone --branch v3.2.1 --depth 1 \
    https://github.com/Netflix/vmaf.git /tmp/vmaf \
    && cd /tmp/vmaf/libvmaf \
    && meson setup build -Dbuilt_in_models=true \
    && meson compile -C build \
    && meson install -C build \
    && echo "/usr/local/lib/aarch64-linux-gnu" > /etc/ld.so.conf.d/libvmaf.conf \
    && ldconfig \
    && rm -rf /tmp/vmaf

# Instalar y compilar librerias de ffmpeg v8.0
RUN git clone --branch n8.0 --depth 1 \
    https://git.ffmpeg.org/ffmpeg.git /tmp/ffmpeg \
    && cd /tmp/ffmpeg \
    && ./configure \
        --enable-version3 \
        --enable-libvmaf \
    && make -j"$(nproc)" \
    && make install \
    && rm -rf /tmp/ffmpeg


# Definir el directorio de trabajo dentro del contenedor
WORKDIR /app

# Agregar las dependencias de sherboa engine
COPY requirements.txt .

# Usar el gestor de paquetes pip para instalar todos los que hay en requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar del directorio actual del proyecto al directorio actual dentro del contenedor
COPY . .

# Comando que se ejecutará cuando se inicie el contenedor:
# uvicorn main:app --host 0.0.0.0 --port 8000 [El servidor acepta conexiones desde cualquier interfaz de red]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]