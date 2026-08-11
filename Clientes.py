import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

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

# Diccionario para convertir números de mes a nombre en español con formato espaciado
meses_nombres = {
    1: "--- E N E R O ---",
    2: "--- F E B R E R O ---",
    3: "--- M A R Z O ---",
    4: "--- A B R I L ---",
    5: "--- M A Y O ---",
    6: "--- J U N I O ---",
    7: "--- J U L I O ---",
    8: "--- A G O S T O ---",
    9: "--- S E P T I E M B R E ---",
    10: "--- O C T U B R E ---",
    11: "--- N O V I E M B R E ---",
    12: "--- D I C I E M B R E ---"
}

def parsear_fecha(fecha_str):
    fecha_str = str(fecha_str).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(fecha_str.split(" ")[0], fmt)
        except ValueError:
            continue
    return None

def reorganizar_con_meses_en_sheet(df_actual):
    # Filtramos filas que no sean divisorias de meses existentes
    registros = []
    for _, row in df_actual.iterrows():
        fact = str(row.get("FACTURA", "")).strip()
        if not fact.startswith("---"):
            registros.append(row.to_dict())
            
    if not registros:
        return []

    # Ordenar registros por fecha
    def clave_orden(r):
        dt = parsear_fecha(r.get("FECHA", ""))
        return dt if dt else datetime.min

    registros.sort(key=clave_orden)

    nueva_data = []
    mes_actual = None

    for reg in registros:
        dt = parsear_fecha(reg.get("FECHA", ""))
        if dt:
            if dt.month != mes_actual:
                mes_actual = dt.month
                nombre_div = meses_nombres.get(mes_actual, "--- MES ---")
                # Fila divisoria abarcando todo el ancho de las columnas
                fila_div = {col: "" for col in df_actual.columns}
                fila_div[df_actual.columns[0]] = nombre_div
                nueva_data.append(fila_div)
        nueva_data.append(reg)

    return nueva_data

# --- INTERFAZ STREAMLIT ---
st.set_page_config(layout="wide")
st.title("Inventario de Clientes y Proveedores")

df = load_data()
st.dataframe(df, use_container_width=True)

# --- FORMULARIO DE ALTA (SIDEBAR) ---
st.sidebar.header("Dar de alta nuevo registro")
with st.sidebar.form("alta_form"):
    factura = st.text_input("FACTURA", key="factura_alta")
    cliente = st.text_input("CLIENTES", key="cliente_alta")
    descripcion = st.text_input("DESCRIPCION", key="descripcion_alta")
    fecha = st.date_input("FECHA", key="fecha_alta")
    subtotal = st.number_input("SUBTOTAL", min_value=0.0, format="%.2f", key="sub_alta")
    iva_input = st.text_input("IVA (Opcional, por defecto 16%)", value="", key="iva_alta")
    isr_input = st.text_input("ISR (Opcional, por defecto 1.25%)", value="", key="isr_alta")
    
    submitted = st.form_submit_button("Guardar")
    
    if submitted:
        if factura and cliente and descripcion and fecha and subtotal >= 0:
            # Validar que la factura no exista (excluyendo filas divisorias)
            facturas_existentes = [str(row.get("FACTURA", "")).strip() for _, row in df.iterrows() if not str(row.get("FACTURA", "")).startswith("---")]
            if factura.strip() in facturas_existentes:
                st.error(f"¡Error! El número de factura '{factura}' ya existe en la base de datos para otro cliente.")
            else:
                # Calcular IVA e ISR manejando campos vacíos o nulos de manera segura
                try:
                    iva = float(iva_input) if iva_input.strip() != "" else subtotal * 0.16
                except ValueError:
                    iva = 0.0

                try:
                    isr = float(isr_input) if isr_input.strip() != "" else subtotal * 0.0125
                except ValueError:
                    isr = 0.0

                total = subtotal + iva + isr
                
                new_row = {
                    "FACTURA": factura.strip(),
                    "CLIENTES": cliente.strip(),
                    "DESCRIPCION": descripcion.strip(),
                    "FECHA": str(fecha),
                    "SUBTOTAL": f"{subtotal:.2f}",
                    "IVA": f"{iva:.2f}",
                    "ISR": f"{isr:.2f}",
                    "TOTAL": f"{total:.2f}",
                    "ESTATUS": "PENDIENTE"
                }
                
                # Agregar y reorganizar con meses en Google Sheets
                current_records = [r for _, r in df.iterrows()] if not df.empty else []
                current_records.append(new_row)
                
                # Reconstruir hoja completa con orden cronológico y divisorias de meses
                temp_df = pd.DataFrame(current_records)
                reorganized = reorganizar_con_meses_en_sheet(temp_df)
                
                headers = list(df.columns) if not df.empty else list(new_row.keys())
                sheet_data = [headers]
                for r in reorganized:
                    sheet_data.append([r.get(h, "") for h in headers])
                    
                sheet.clear()
                sheet.update("A1", sheet_data)
                st.success("Datos guardados y organizados por mes correctamente")
                st.rerun()
        else:
            st.error("Por favor completa todos los campos obligatorios.")

# --- EDITAR O ELIMINAR REGISTROS ---
st.markdown("---")
with st.expander("✏️ Editar o Eliminar Registros"):
    if df.empty:
        st.info("No hay registros suficientes para editar.")
    else:
        opciones_registros = []
        indices_reales = []
        
        for idx, row in df.iterrows():
            fact = str(row.get('FACTURA', '')).strip()
            if fact and not fact.startswith("---"):
                label = f"Factura: {fact} | Cliente: {row.get('CLIENTES', '')}"
                opciones_registros.append(label)
                indices_reales.append(idx + 2) # +2 por cabecera y base 0
                
        if opciones_registros:
            seleccion = st.selectbox("Selecciona el registro a modificar", options=opciones_registros, key="select_edit")
            
            if seleccion:
                idx_seleccionado = indices_reales[opciones_registros.index(seleccion)]
                fila_actual = sheet.row_values(idx_seleccionado)
                
                while len(fila_actual) < 9:
                    fila_actual.append("")
                
                with st.form("edit_form"):
                    e_factura = st.text_input("Factura", value=fila_actual[0], key="e_fact")
                    e_cliente = st.text_input("Clientes", value=fila_actual[1], key="e_cli")
                    e_descripcion = st.text_input("Descripción", value=fila_actual[2], key="e_desc")
                    e_fecha = st.text_input("Fecha (YYYY-MM-DD)", value=fila_actual[3], key="e_fec")
                    
                    try:
                        sub_val = float(fila_actual[4])
                    except ValueError:
                        sub_val = 0.0
                        
                    e_subtotal = st.number_input("Subtotal", value=sub_val, format="%.2f", key="e_sub")
                    e_iva_input = st.text_input("IVA", value=fila_actual[5], key="e_iva")
                    e_isr_input = st.text_input("ISR", value=fila_actual[6], key="e_isr")
                    
                    idx_estatus = 0 if fila_actual[8] != "PAGADA" else 1
                    e_estatus = st.selectbox("Estatus", options=["PENDIENTE", "PAGADA"], index=idx_estatus, key="e_est")
                    
                    col1, col2 = st.columns(2)
                    actualizar = col1.form_submit_button("Actualizar Registro")
                    eliminar = col2.form_submit_button("Eliminar Registro")
                    
                    if actualizar:
                        # Validar duplicados de factura al editar (excluyendo la fila actual)
                        facturas_existentes = []
                        for i, r in df.iterrows():
                            if (i + 2) != idx_seleccionado:
                                f_val = str(r.get("FACTURA", "")).strip()
                                if f_val and not f_val.startswith("---"):
                                    facturas_existentes.append(f_val)
                                    
                        if e_factura.strip() in facturas_existentes:
                            st.error(f"¡Error! El número de factura '{e_factura}' ya pertenece a otro registro.")
                        else:
                            try:
                                e_iva = float(e_iva_input) if e_iva_input.strip() != "" else e_subtotal * 0.16
                            except ValueError:
                                e_iva = 0.0

                            try:
                                e_isr = float(e_isr_input) if e_isr_input.strip() != "" else e_subtotal * 0.0125
                            except ValueError:
                                e_isr = 0.0

                            e_total = e_subtotal + e_iva + e_isr
                            
                            updated_row = {
                                "FACTURA": e_factura.strip(),
                                "CLIENTES": e_cliente.strip(),
                                "DESCRIPCION": e_descripcion.strip(),
                                "FECHA": e_fecha.strip(),
                                "SUBTOTAL": f"{e_subtotal:.2f}",
                                "IVA": f"{e_iva:.2f}",
                                "ISR": f"{e_isr:.2f}",
                                "TOTAL": f"{e_total:.2f}",
                                "ESTATUS": e_estatus
                            }
                            
                            # Actualizar lista general y reorganizar hoja completa
                            current_records = []
                            for i, r in df.iterrows():
                                if (i + 2) == idx_seleccionado:
                                    current_records.append(updated_row)
                                else:
                                    f_val = str(r.get("FACTURA", "")).strip()
                                    if not f_val.startswith("---"):
                                        current_records.append(r.to_dict())
                                        
                            temp_df = pd.DataFrame(current_records)
                            reorganized = reorganizar_con_meses_en_sheet(temp_df)
                            
                            headers = list(df.columns)
                            sheet_data = [headers]
                            for r in reorganized:
                                sheet_data.append([r.get(h, "") for h in headers])
                                
                            sheet.clear()
                            sheet.update("A1", sheet_data)
                            st.success("¡Registro actualizado correctamente!")
                            st.rerun()
                        
                    if eliminar:
                        sheet.delete_rows(idx_seleccionado)
                        st.success("¡Registro eliminado correctamente!")
                        st.rerun()
        else:
            st.warning("No se encontraron registros válidos para modificar.")
```[cite: 8]