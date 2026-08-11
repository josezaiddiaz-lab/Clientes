import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURACION DE GOOGLE SHEETS ---
# Usamos st.secrets para obtener las credenciales de forma segura
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Cargamos el diccionario de credenciales desde los secretos de Streamlit
creds_dict = dict(st.secrets["gcp_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Abre la hoja de cálculo por nombre
sheet = client.open('Clientes y Proveedores').sheet1

def load_data():
    # Obtener todos los datos
    data = sheet.get_all_values()
    # Asumimos que la primera fila son los encabezados
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

# --- INTERFAZ STREAMLIT ---
st.set_page_config(layout="wide")
st.title("Inventario de Clientes y Proveedores")

# Cargar datos
df = load_data()
st.dataframe(df, use_container_width=True)

# --- FORMULARIO DE ALTA ---
st.sidebar.header("Dar de alta nuevo cliente")
with st.sidebar.form("alta_form"):
    factura = st.text_input("FACTURA", key="factura")
    cliente = st.text_input("CLIENTES", key="cliente")
    descripcion = st.text_input("DESCRIPCION", key="descripcion")
    fecha = st.date_input("FECHA")
    subtotal = st.number_input("SUBTOTAL", min_value=0.0, format="%.2f")
    
    submitted = st.form_submit_button("Guardar")
    
    if submitted:
        if factura and cliente and descripcion and fecha and subtotal:
            # Cálculos automáticos
            iva = subtotal * 0.16
            isr = subtotal * 0.0125
            total = subtotal + iva + isr
            
            # Preparar fila
            # Aseguramos que los valores sean strings o números según lo que espere Sheets
            new_row = [factura, cliente, descripcion, str(fecha), subtotal, iva, isr, total, "PENDIENTE"]
            
            # Guardar en Google Sheet
            sheet.append_row(new_row)
            st.success("Datos guardados correctamente")
            st.rerun()
        else:
            st.error("Por favor completa todos los campos obligatorios.")