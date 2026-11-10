#!/usr/bin/env python
"""Paso 7 - Meteorologia horaria ERA5 (Open-Meteo Historical Weather API) en el punto de ignicion de cada caso,
desde fecha_inicio 00:00 hasta fecha_fin 23:00 hora local (UTC-3)."""
import json
import os
import time
import urllib.parse
import urllib.request

import pandas as pd

CP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://archive-api.open-meteo.com/v1/archive"
MODELO = "era5"
FUENTE = "ERA5 (ECMWF/Copernicus C3S) via Open-Meteo Historical Weather API, models=era5"
UTC_OFFSET_H = -3  # America/Argentina/San_Luis, sin horario de verano desde 2009
FECHA_DESCARGA = pd.Timestamp.now().date().isoformat()

# variable Open-Meteo -> columna de salida (unidades en el nombre)
VARS = {
    "temperature_2m": "temp_2m_c",
    "dew_point_2m": "punto_rocio_2m_c",
    "relative_humidity_2m": "hr_2m_pct",
    "precipitation": "precipitacion_mm",
    "rain": "lluvia_mm",
    "pressure_msl": "presion_nivel_mar_hpa",
    "surface_pressure": "presion_superficie_hpa",
    "wind_speed_10m": "viento_vel_10m_ms",
    "wind_direction_10m": "viento_dir_10m_grados",
    "wind_gusts_10m": "viento_rafaga_10m_ms",
    "cloud_cover": "nubosidad_pct",
    "shortwave_radiation": "radiacion_onda_corta_wm2",
    "vapour_pressure_deficit": "dpv_kpa",
    "et0_fao_evapotranspiration": "et0_fao_mm",
    "soil_moisture_0_to_7cm": "humedad_suelo_0_7cm_m3m3",
}


def consultar(lat, lon, desde, hasta):
    params = dict(latitude=lat, longitude=lon, start_date=desde, end_date=hasta, hourly=",".join(VARS),
                  models=MODELO, wind_speed_unit="ms", timezone="GMT")
    url = URL + "?" + urllib.parse.urlencode(params)
    for intento in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except Exception as e:  # reintento simple ante errores de red o limite de la API
            if intento == 3:
                raise
            print(f"  reintento {intento + 1}: {e}")
            time.sleep(5 * (intento + 1))


def main():
    idx = pd.read_csv(os.path.join(CP, "indice_casos.csv"))
    tablas = []
    for c in idx.itertuples():
        ini_local = pd.Timestamp(c.fecha_inicio)
        fin_local = pd.Timestamp(c.fecha_fin) + pd.Timedelta(hours=23)
        ini_utc = ini_local - pd.Timedelta(hours=UTC_OFFSET_H)
        fin_utc = fin_local - pd.Timedelta(hours=UTC_OFFSET_H)
        js = consultar(c.lat_ign, c.lon_ign, ini_utc.date().isoformat(), fin_utc.date().isoformat())
        h = pd.DataFrame(js["hourly"])
        utc = pd.to_datetime(h.pop("time"))
        h = h[(utc >= ini_utc) & (utc <= fin_utc)].rename(columns=VARS)
        utc = utc[h.index]
        t0 = pd.Timestamp(c.t0_utc).tz_localize(None)
        df = pd.DataFrame({
            "case_id": c.case_id,
            "fecha_hora_local": (utc + pd.Timedelta(hours=UTC_OFFSET_H)).dt.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
            "fecha_hora_utc": utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "minutos_desde_t0": ((utc - t0).dt.total_seconds() // 60).astype(int),
            "lat_consulta": c.lat_ign,
            "lon_consulta": c.lon_ign,
            "lat_celda_era5": round(js["latitude"], 4),
            "lon_celda_era5": round(js["longitude"], 4),
            "elevacion_dem_m": js["elevation"],
        })
        df = pd.concat([df, h[list(VARS.values())]], axis=1)
        df["fuente"] = FUENTE
        esperadas = int((fin_utc - ini_utc) / pd.Timedelta(hours=1)) + 1
        assert len(df) == esperadas, f"{c.case_id}: {len(df)} filas, se esperaban {esperadas}"
        faltantes = int(df[list(VARS.values())].isna().sum().sum())
        df.to_csv(os.path.join(CP, c.ruta_caso, "meteo_horaria.csv"), index=False, lineterminator="\n")
        tablas.append(df)
        print(f"{c.case_id}: {len(df)} h | celda ERA5 ({js['latitude']:.2f}, {js['longitude']:.2f}) | "
              f"T {df.temp_2m_c.min():.1f}..{df.temp_2m_c.max():.1f} C | HR min {df.hr_2m_pct.min():.0f} % | "
              f"viento max {df.viento_vel_10m_ms.max():.1f} m/s (rafaga {df.viento_rafaga_10m_ms.max():.1f}) | "
              f"lluvia {df.precipitacion_mm.sum():.1f} mm | celdas vacias {faltantes}")
        time.sleep(1)
    total = pd.concat(tablas, ignore_index=True)
    total.to_csv(os.path.join(CP, "meteo_casos_horaria.csv"), index=False, lineterminator="\n")
    print(f"meteo_casos_horaria.csv: {len(total)} filas, {total.case_id.nunique()} casos")
    actualizar_readme(total)


def num(x, d=1):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


def actualizar_readme(total):
    """06_controles_reporte.py reescribe el README: este paso (re)inserta su seccion y sus lineas sin duplicarlas."""
    ruta = os.path.join(CP, "README.md")
    with open(ruta, encoding="utf-8") as f:
        txt = f.read()
    txt = txt.replace("Generado por `scripts/ejecutar_todo.sh` (scripts 01 a 06).",
                      "Generado por `scripts/ejecutar_todo.sh` (scripts 01 a 06; el 07 agrega la meteorología, ver sección (6)).")
    fila = ("| meteo_horaria.csv | meteorología horaria ERA5 en el punto de ignición, de `fecha_inicio` 00:00 a "
            "`fecha_fin` 23:00 local (ver sección (6)) |")
    ancla = "| curva_area_tiempo.csv | N2: superficie por fecha con su fuente por fila |"
    if fila not in txt:
        txt = txt.replace(ancla, ancla + "\n" + fila)
    paso = ("7. Forzantes meteorológicos: `casos/<case_id>/meteo_horaria.csv`, que tiene una fila por hora e incluye "
            "`minutos_desde_t0` (ver sección (6)).")
    ancla = "No se reasignan después de ver resultados."
    if paso not in txt:
        txt = txt.replace(ancla, ancla + "\n" + paso, 1)

    filas = []
    for cid, d in total.groupby("case_id", sort=False):
        filas.append(f"| {cid} | {len(d)} | {num(d.lat_celda_era5.iloc[0], 2)}; {num(d.lon_celda_era5.iloc[0], 2)} | "
                     f"{num(d.temp_2m_c.min())}–{num(d.temp_2m_c.max())} | {d.hr_2m_pct.min():.0f} | "
                     f"{num(d.viento_vel_10m_ms.max())} / {num(d.viento_rafaga_10m_ms.max())} | "
                     f"{num(d.precipitacion_mm.sum())} |")
    celdas = total.groupby(["lat_celda_era5", "lon_celda_era5"]).case_id.unique()
    compartidas = [(k, v) for k, v in celdas.items() if len(v) > 1]
    txt_compartidas = "".join(
        f"\n  - **{', '.join(c[:4] for c in v[:-1])} y {v[-1][:4]} caen en la misma celda** "
        f"({num(k[0], 2)}; {num(k[1], 2)}), así que sus series solo difieren por la fecha y por el ajuste de elevación."
        for k, v in compartidas)
    seccion = f"""## (6) Meteorología por caso (agregado el {FECHA_DESCARGA})

Se agregó la meteorología **horaria** de todas las fechas entre el inicio y el fin de cada incendio. La genera `scripts/07_meteorologia.py`, que no modifica ningún archivo anterior.

**Archivos**
- `meteo_casos_horaria.csv` (raíz): consolidado de los {total.case_id.nunique()} casos, con {len(total)} filas y columna `case_id`.
- `casos/<case_id>/meteo_horaria.csv`: el mismo contenido separado por caso.
- Columnas y unidades en `00_metadatos/esquema_columnas.md`. Decisiones en D28 a D31 de `decisiones_log.md`.

**Período.** Desde `fecha_inicio` 00:00 hasta `fecha_fin` 23:00, en hora local (UTC−3), ambos días incluidos. `minutos_desde_t0` usa el mismo `t0_utc` del caso, que vale 0 a las 12:00 locales del primer día. Los valores negativos son horas previas a t0.

**Variables:**
- temperatura y punto de rocío a 2 m (°C);
- humedad relativa (%);
- precipitación total y lluvia (mm/h);
- presión a nivel del mar y presión en superficie (hPa);
- viento a 10 m: velocidad y ráfaga (m/s) y dirección (grados, de donde viene el viento; 0 = norte);
- nubosidad (%);
- radiación de onda corta (W/m²);
- déficit de presión de vapor (kPa);
- evapotranspiración de referencia FAO (mm);
- humedad del suelo de 0 a 7 cm (m³/m³).

| case_id | horas | celda ERA5 (lat, lon) | T mín–máx (°C) | HR mín (%) | viento máx / ráfaga (m/s) | lluvia (mm) |
|---|---:|---|---|---:|---|---:|
{chr(10).join(filas)}

**Fuente**
- **Datos:** reanálisis **ERA5** del ECMWF, servicio Copernicus Climate Change Service (C3S). Hersbach, H. et al. (2020). *The ERA5 global reanalysis*. Q. J. R. Meteorol. Soc. 146: 1999–2049. https://doi.org/10.1002/qj.3803. Conjunto de datos: https://doi.org/10.24381/cds.adbb2d47.
- **Acceso:** Open-Meteo Historical Weather API (`{URL}`, parámetro `models={MODELO}`). Zippenfeld, P. (2023). *Open-Meteo.com Weather API*. Zenodo. https://doi.org/10.5281/zenodo.7970649. Licencia de los datos: CC BY 4.0. Fecha de descarga: {FECHA_DESCARGA}.

**Limitaciones (dato de modelo, no observado)**
- ERA5 es un **reanálisis**, no una medición en el sitio. La grilla es de 0,25° (unos 28 km): cada caso toma la celda más cercana y el relieve serrano queda suavizado.{txt_compartidas}
  - Las brisas de valle y ladera y la canalización del viento en quebradas no están representadas.
- Open-Meteo ajusta la temperatura y la presión en superficie a la elevación del punto consultado, tomada de un MDE de 90 m (`elevacion_dem_m`). Es un ajuste estadístico, no un dato observado.
- En SM05, el punto de ignición del parte representa mal un complejo de 9 fragmentos y unos 38 600 ha. El viento puede variar dentro del bbox.
- No se contrastó con estaciones. La estación SMN más cercana (San Luis Aero, 87436) queda a unos 70–90 km, en otro relieve. Queda como pendiente.

"""
    ini = txt.find("## (6) Meteorología por caso")
    fin = txt.find("## Archivos de metadatos")
    txt = txt[:ini] + seccion + txt[fin:] if ini != -1 else txt[:fin] + seccion + txt[fin:]
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    print("README.md: seccion (6) actualizada")


if __name__ == "__main__":
    main()
