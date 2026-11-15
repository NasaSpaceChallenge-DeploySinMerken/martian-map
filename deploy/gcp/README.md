# Despliegue automático en Google Cloud

Cada push a `develop` ejecuta `.github/workflows/deploy-gcp.yml`: prueba Python,
construye el mapa, despliega `martian-layers` en Cloud Run y publica el paquete
de análisis en `gs://martian-map-javier-2026-releases/analysis-release.zip`.
La VM `martian-analysis` comprueba ese objeto cada minuto con
`martian-analysis-update.timer`, valida el ZIP, instala dependencias y reinicia
el servicio. Si la nueva versión no responde a `/health`, restaura el ZIP anterior.
El DEM permanece en la VM y en su bucket de datos; no se sube a GitHub Actions.

GitHub usa Workload Identity Federation (proveedor `martian-map-develop`) con la
cuenta `gha-martian-back@martian-map-javier-2026.iam.gserviceaccount.com`. El
proveedor acepta solo el ID del repositorio `1457833814` y `refs/heads/develop`.
No se usan claves JSON. La cuenta de CI puede desplegar Cloud Run y escribir en
el bucket de releases; no tiene escritura en el bucket del DEM. Cloud Run usa la
cuenta de ejecución `martian-layers-runtime` y sigue requiriendo autenticación.

Para comprobar la VM:

```bash
sudo systemctl status martian-analysis-update.timer
sudo journalctl -u martian-analysis-update.service -n 40 --no-pager
cat /opt/martian-analysis/installed.sha256
curl -fsS http://127.0.0.1:8000/health
```

El paquete se genera con `python deploy/gcp/package.py`; su ZIP es determinista,
así que un cambio solo en el mapa no reinicia la VM.
