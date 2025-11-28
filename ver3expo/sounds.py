import wave
import math
import struct
import os

def write_wav(filename, duration, freq, volume=0.5, wave_type='sine'):
    # Configuración de audio
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    
    # Asegurar que la carpeta existe
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with wave.open(filename, 'w') as wav_file:
        # (nchannels, sampwidth, framerate, nframes, comptype, compname)
        wav_file.setparams((1, 2, sample_rate, n_samples, 'NONE', 'not compressed'))
        
        values = []
        for i in range(n_samples):
            t = i / sample_rate
            if wave_type == 'sine':
                # Onda senoidal (suave, para el tick)
                val = math.sin(2 * math.pi * freq * t)
            elif wave_type == 'saw':
                # Onda diente de sierra (áspera, para el timeout)
                val = 2 * (t * freq - math.floor(0.5 + t * freq))
            else:
                val = 0
            
            # Escalar volumen y convertir a entero de 16 bits
            packed_val = struct.pack('h', int(val * volume * 32767.0))
            wav_file.writeframes(packed_val)
            
    print(f"Generado: {filename}")

# 1. Generar TICK (Corto, agudo, tipo reloj)
# 0.05 segundos, 800Hz
write_wav("sounds/tick.wav", duration=0.05, freq=800, volume=0.3, wave_type='sine')

# 2. Generar TIMEOUT (Largo, grave, tipo error)
# 1.0 segundo, 150Hz descendiendo (simulado simple aquí como constante grave)
write_wav("sounds/timeout.wav", duration=0.8, freq=120, volume=0.5, wave_type='saw')

print("\n¡Listo! Carpeta 'sounds' creada con tick.wav y timeout.wav")