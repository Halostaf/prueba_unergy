# -*- coding: utf-8 -*-
"""
Created on Thu Jan 30 15:27:13 2025

@author: jamas
"""
import matplotlib.pyplot as plt
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta

start_date = datetime.strptime("15-03-2024 00:00:00", "%d-%m-%Y %H:%M:%S")
end_date = datetime.strptime("15-04-2024 00:00:00", "%d-%m-%Y %H:%M:%S")

# Extraer datos del API
url = "https://l2h237eh53.execute-api.us-east-1.amazonaws.com/dev/precios?start_date=2024-03-15&end_date=2024-04-14"

response = requests.get(url)

if response.status_code == 200:
    data = response.json()
else:
    print("Error al obtener los datos", response.status_code)
    exit()
    
# Extraer el diccionario data (diccionario) y separarlo
precios_data = data["data"]

# Convertir el diccionario en una lista de tuplas (fecha, hora, precio)
# Convierte las hotas de 24:00 a 00:00 mientras lo recorre
lista_precios = [
    (fecha,"00:00" if hora == "24:00" else hora, precio)
    for fecha, horas in precios_data.items()
    for hora, precio in horas.items()
]

# Crearmos el DataFrame
df = pd.DataFrame(lista_precios, columns=["Fecha", "Hora", "Precio"]) 
# Ordenar por fecha y hora
df = df.sort_values(by=["Fecha", "Hora"]) 

# Fusionamos Fecha y Hora en una columna datetime
df["Datetime"] = pd.to_datetime(df["Fecha"] + " " + df["Hora"], format="%Y-%m-%d %H:%M")

# Crear una lista con todas las fechas y horas dentro del rango
all_dates = pd.date_range(start=start_date, end=end_date - timedelta(seconds=1), freq="H")
full_df = pd.DataFrame({"Datetime": all_dates})

# Identificar valores faltantes antes del tratamiento
def identificar_faltantes(df, full_df):
    # merge ayuda a verificar los datos que hayan en los 2 dataframe, uno
    # se encuentra con toda las fechas del rango y otra con las obtenidas en la api
    # se comparan y se fusionan teniendo en cuenta que habian datos faltantes
    merged_df = full_df.merge(df, on="Datetime", how="left", indicator=True)
    missing_data = merged_df[merged_df["_merge"] == "left_only"]["Datetime"]
    print("Valores faltantes antes del tratamiento de datos:")
    print(missing_data.dt.strftime("%Y-%m-%d %H:%M").tolist())
    return missing_data
# Aqui se imprimen los dias faltantes
faltantes = identificar_faltantes(df, full_df)

# Unir con los datos originales
df = full_df.merge(df, on="Datetime", how="left")

# Llenar valores faltantes en horas con el último dato disponible
df["Precio"] = df["Precio"].ffill()

# Función para rellenar los días faltantes con el promedio de los 3 días anterioress y posteriores
def dias_faltantes(df):
    df["Fecha"] = df["Datetime"].dt.date  # Extraer solo la fecha (Sin la hora)
    unique_dates = df["Fecha"].unique() # Lisra de fechas en el dataframe
    
    for date in unique_dates:
        day_data = df[df["Fecha"] == date]
        
        if day_data["Precio"].isna().all():  # Si ¿todo el día está vacío?
            prev_days = df[(df["Fecha"] >= date - timedelta(days=3)) & (df["Fecha"] < date)]["Precio"]
            next_days = df[(df["Fecha"] > date) & (df["Fecha"] <= date + timedelta(days=3))]["Precio"]
            
            # Calcula los promedios
            mean_value = pd.concat([prev_days, next_days]).mean()
            
            # Rellena los datos
            df.loc[df["Fecha"] == date, "Precio"] = mean_value
    
    return df

df = dias_faltantes(df)

# Calcular el promedio diario de precios
df["Fecha"] = df["Datetime"].dt.strftime("%Y-%m-%d")
promedio_diario = df.groupby("Fecha")["Precio"].mean().reset_index() # Agrupa por fecha para calcular el promedio
promedio_diario.rename(columns={"Precio": "Promedio_Diario"}, inplace=True)

# Calcular el promedio móvil de 7 días
promedio_diario["Promedio_Movil_7d"] = promedio_diario["Promedio_Diario"].rolling(window=7).mean()

# Volver a separar en "Fecha" y "Hora"
df["Hora"] = df["Datetime"].dt.strftime("%H:%M")

# Eliminar la columna extra "Datetime"
df = df[["Fecha", "Hora", "Precio"]]

# Mostrar los primeros datos
print(df.head(30))

# Mostrar el promedio diario y el promedio móvil de 7 días
print("\nPromedio diario de precios:")
print(promedio_diario.head(30))

# Generar la gráfica
plt.figure(figsize=(12, 6))
plt.plot(promedio_diario["Fecha"], promedio_diario["Promedio_Diario"], label="Promedio Diario", marker="o")
plt.plot(promedio_diario["Fecha"], promedio_diario["Promedio_Movil_7d"], label="Promedio Móvil 7 días", linestyle="dashed")
plt.xlabel("Fecha")
plt.ylabel("Precio")
plt.title("Comparación del Promedio Diario y Promedio Móvil de 7 días")
plt.legend()
plt.xticks(rotation=90)
plt.grid()
plt.tight_layout()

# Guardar la gráfica como imagen
plt.savefig("image.png")
plt.show()

# Guardar los resultados en una base de datos SQLite
conn = sqlite3.connect("precios.db")
c = conn.cursor()

# Crear la tabla si no existe
c.execute('''
    CREATE TABLE IF NOT EXISTS precios_diarios (
        fecha TEXT PRIMARY KEY,
        precio_promedio REAL,
        precio_7d REAL
    )
''')

# Insertar los datos en la tabla iterando filas
for index, row in promedio_diario.iterrows():
    c.execute('''
        INSERT INTO precios_diarios (fecha, precio_promedio, precio_7d)
        VALUES (?, ?, ?)
        ON CONFLICT(fecha) DO UPDATE SET
            precio_promedio = excluded.precio_promedio,
            precio_7d = excluded.precio_7d
    ''', (row["Fecha"], row["Promedio_Diario"], row["Promedio_Movil_7d"]))

# Guardar cambios y cerrar conexión
conn.commit()
conn.close()

print("Los resultados han sido almacenados en la base de datos SQLite 'precios.db'.")
