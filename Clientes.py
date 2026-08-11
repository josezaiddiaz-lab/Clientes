import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURACION DE GOOGLE SHEETS ---
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

creds_dict = dict(st.secrets["gcp_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open('Clientes y Proveedores').sheet1

def load_data():
    data = sheet.get_all_values()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

# --- INTERFAZ STREAMLIT ---
st.set_page_config(layout="wide")
st.title("Inventario de Clientes y Proveedores")

# Cargar datos
df = load_data()
st.dataframe(df, use_container_width=True)

# --- FORMULARIO DE ALTA (SIDEBAR) ---
st.sidebar.header("Dar de alta nuevo registro")
with st.sidebar.form("alta_form"):
    factura = st.text_input("FACTURA", key="factura")
    cliente = st.text_input("CLIENTES", key="cliente")
    descripcion = st.text_input("DESCRIPCION", key="descripcion")
    fecha = st.date_input("FECHA")
    subtotal = st.number_input("SUBTOTAL", min_value=0.0, format="%.2f")
    
    submitted = st.form_submit_button("Guardar")
    
    if submitted:
        if factura and cliente and descripcion and fecha and subtotal:
            iva = subtotal * 0.16
            isr = subtotal * 0.0125
            total = subtotal + iva + isr
            
            new_row = [factura, cliente, descripcion, str(fecha), f"{subtotal:.2f}", f"{iva:.2f}", f"{isr:.2f}", f"{total:.2f}", "PENDIENTE"]
            sheet.append_row(new_row)
            st.success("Datos guardados correctamente")
            st.rerun()
        else:
            st.error("Por favor completa todos los campos obligatorios.")

# --- EDITAR O ELIMINAR REGISTROS ---
st.markdown("---")
with st.expander("✏️ Editar o Eliminar Registros"):
    if df.empty or len(df) <= 1:
        st.info("No hay registros suficientes para editar.")
    else:
        # Creamos opciones legibles para el selectbox basadas en las filas existentes (ignorando encabezados si fuera necesario)
        opciones_registros = []
        indices_reales = []
        
        for idx, row in df.iterrows():
            # Omitir filas vacías o de títulos como 'ENERO' si las hay
            if row['FACTURA'] and row['FACTURA'] != "ENERO":
                label = f"Fila {idx + 2} - Factura: {row['FACTURA']} | Cliente: {row['CLIENTES']}"
                opciones_registros.append(label)
                indices_reales.append(idx + 2) # +2 por el encabezado y el índice base 0 de pandas
                
        if opciones_registros:
            seleccion = st.selectbox("Selecciona el registro a modificar", options=opciones_registros)
            
            if seleccion:
                # Extraer la fila real de Google Sheets
                idx_seleccionado = indices_reales[opciones_registros.index(seleccion)]
                fila_actual = sheet.row_values(idx_seleccionado)
                
                # Asegurar que la fila tenga los elementos necesarios
                while len(fila_actual) < 9:
                    fila_actual.append("")
                
                with st.form("edit_form"):
                    e_factura = st.text_input("Factura", value=fila_actual[0])
                    e_cliente = st.text_input("Clientes", value=fila_actual[1])
                    e_descripcion = st.text_input("Descripción", value=fila_actual[2])
                    e_fecha = st.text_input("Fecha", value=fila_actual[3])
                    
                    try:
                        sub_val = float(fila_actual[4])
                    except:
                        sub_val = 0.0
                        
                    e_subtotal = st.number_input("Subtotal", value=sub_val, format="%.2f")
                    e_estatus = st.selectbox("Estatus", options=["PENDIENTE", "PAGADA"], index=0 if fila_actual[8] != "PAGADA" else 1)
                    
                    col1, col2 = st.columns(2)
                    actualizar = col1.form_submit_button("Actualizar Registro")
                    eliminar = col2.form_submit_button("Eliminar Registro")
                    
                    if actualizar:
                        e_iva = e_subtotal * 0.16
                        e_isr = e_subtotal * 0.0125
                        e_total = e_subtotal + e_iva + e_isr
                        
                        updated_row = [e_factura, e_cliente, e_descripcion, e_fecha, f"{e_subtotal:.2f}", f"{e_iva:.2f}", f"{e_isr:.2f}", f"{e_total:.2f}", e_estatus]
                        
                        # Actualizar en Google Sheets (rango de la fila A hasta I)
                        sheet.update(f"A{idx_seleccionado}:I{idx_seleccionado}", [updated_row])
                        st.success("¡Registro actualizado correctamente!")
                        st.rerun()
                        
                    if eliminar:
                        sheet.delete_rows(idx_seleccionado)
                        st.success("¡Registro eliminado correctamente!")
                        st.rerun()
        else:
            st.warning("No se encontraron registros válidos para modificar.")