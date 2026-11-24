"""Analiza la captura generada por Webots; requiere numpy/opencv/matplotlib."""
from pathlib import Path
import csv
import numpy as np
import cv2
import matplotlib.pyplot as plt

base = Path(__file__).resolve().parents[1]
folder = base / 'capturas'
with (folder / 'depth.csv').open(newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    hdr = next(reader)
    width, height = int(hdr[1]), int(hdr[3])
    depth = np.array([[float(v) for v in row] for row in reader], dtype=np.float32)
assert depth.shape == (height, width), (depth.shape, height, width)
ruta_rgb = folder / 'rgb.png'
if not ruta_rgb.is_file():
    raise FileNotFoundError(f'No existe {ruta_rgb}; verifica la consola de Webots.')
# Evitamos que cv2.imread falle en Windows con rutas que contienen tildes.
rgb = cv2.imdecode(np.frombuffer(ruta_rgb.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
if rgb is None:
    raise ValueError(f'La imagen RGB no se pudo decodificar: {ruta_rgb}')
# Evitar usar 0 o infinito como si fueran distancias validas.
valid = np.isfinite(depth) & (depth > 0)
clean = depth.copy()
clean[~valid] = np.nan
h, w = depth.shape
labels = []
for n, name in enumerate(('Izquierda','Centro','Derecha')):
    roi = clean[int(.28*h):int(.64*h),n*w//3:(n+1)*w//3]
    finite = roi[np.isfinite(roi)]
    if len(finite) < .1*roi.size:
        labels.append(f'{name}: DESCONOCIDO')
    else:
        d = np.percentile(finite,20)
        labels.append(f'{name}: {d:.2f}m / {"OCUPADO" if d < 1.05 else "LIBRE"}')
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
ax[0].imshow(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))
ax[0].set_title('RGB simulada')
for fraction in (1/3,2/3):
    ax[0].axvline(rgb.shape[1]*fraction,color='white',linestyle='--',alpha=.8)
img = ax[1].imshow(clean,cmap='turbo',vmin=.80,vmax=3.5)
ax[1].set_title('Profundidad simulada (m)')
for fraction in (1/3,2/3):
    ax[1].axvline(w*fraction,color='white',linestyle='--',alpha=.8)
fig.colorbar(img,ax=ax[1],fraction=.046,pad=.04)
for a in ax:
    a.axis('off')
fig.suptitle(' | '.join(labels),fontsize=10)
fig.tight_layout()
# Guardado compatible con rutas Unicode de Windows.
from io import BytesIO
buf = BytesIO()
fig.savefig(buf, format='png', dpi=150)
(folder / 'analisis_rgbd.png').write_bytes(buf.getvalue())
plt.close(fig)
print('\n'.join(labels))
print('Resultado:',folder/'analisis_rgbd.png')
