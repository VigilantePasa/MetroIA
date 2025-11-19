import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import json
import requests
from datetime import datetime, timedelta

# Variables globales
RUTA_MAPA = "MapaMetroCDMRecortado.png"
RUTA_COORDS = "coords.json"
URL_BACKEND = "http://127.0.0.1:8000"

def obtener_estaciones():
    try:
        resp = requests.get(f"{URL_BACKEND}/stations")
        resp.raise_for_status()
        datos = resp.json()
        return datos.get("stations", [])
    except Exception as e:
        print("Error al obtener estaciones:", e)
        return []

class MetroGUI:
    def __init__(self, raiz):
        self.raiz = raiz
        self.raiz.title("Metro CDMX – GUI A*")

        # Maximizamos la pantalla
        raiz.state("zoomed")

        # Cargamos las coordenadas de las estaciones
        with open(RUTA_COORDS, "r", encoding="utf-8") as f:
            self.coordenadas = json.load(f)

        # Colores de líneas
        self.COLORES_LINEAS = {"L1": "#FF3971", "L3": "#77EE3C", "L7": "#FFD23F",
                               "L9": "#7A512B", "L12": "#779156"}
        
        # Imagenes lineas 
        self.IMAGENES_LINEAS = {"L1": "L1.png", "L3": "L3.png", "L7": "L7.png",
                               "L9": "L9.png", "L12": "L12.png"}
        # Guardar las referenias a esas imagenes
        self.imgs_lineas_panel = []

        # Obtener tamaño de pantalla
        raiz.update_idletasks()
        self.ancho_pantalla = raiz.winfo_width()
        self.alto_pantalla = raiz.winfo_height()

        # Cargar imagen y escalar
        imagen_original = Image.open(RUTA_MAPA)
        self.ancho_original = imagen_original.width
        self.alto_original = imagen_original.height
        self.escala = (self.alto_pantalla * 0.85) / self.alto_original
        ancho_nuevo = int(self.ancho_original * self.escala)
        alto_nuevo = int(self.alto_original * self.escala)
        self.imagen_mapa = imagen_original.resize((ancho_nuevo, alto_nuevo), Image.LANCZOS)
        self.tk_imagen = ImageTk.PhotoImage(self.imagen_mapa)

        # Calcular offsets para centrar
        self.offset_x = (self.ancho_pantalla - ancho_nuevo) // 2
        self.offset_y = (self.alto_pantalla - alto_nuevo) // 2

        # Crear overlay transparente
        self.overlay = Image.new("RGBA", (ancho_nuevo, alto_nuevo), (0, 0, 0, 0))
        self.dibujo = ImageDraw.Draw(self.overlay)
        self.tk_overlay = ImageTk.PhotoImage(self.overlay)

        # Crear canvas del tamaño de la pantalla
        self.canvas = tk.Canvas(raiz, width=self.ancho_pantalla, height=self.alto_pantalla, bg="white")
        self.canvas.pack(fill="both", expand=True)

        # Pintar imagen centrada y overlay
        self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.tk_imagen)
        self.id_overlay = self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.tk_overlay)

        # Panel lateral izquierdo 
        ancho_panel = int(self.ancho_pantalla * 0.22)
        self.panel_lateral = tk.Frame(raiz, bg="white", width=ancho_panel)
        self.panel_lateral.place(x=50, y=50)

        # Obtener estaciones
        self.estaciones = obtener_estaciones()

        # Estilo para Combobox
        style = ttk.Style()
        style.theme_use("default")

        style.configure("Custom.TCombobox",
                fieldbackground="#46d4ff",   
                background="#46e3ff",        
                foreground="blue",          
                bordercolor="black",         
                selectbackground="#46e3ff",  
                selectforeground="blue",    
                padding=5)
        
        # Combobox Origen
        tk.Label(self.panel_lateral, text="ORIGEN:", font=("Arial", 12, "bold"), bg="white", fg="blue").pack(anchor="w")
        self.combo_origen = ttk.Combobox(self.panel_lateral, values=self.estaciones, width=50, style="Custom.TCombobox")
        self.combo_origen.pack(pady=10)

        # Combobox Destino
        tk.Label(self.panel_lateral, text="DESTINO:", font=("Arial", 12, "bold"), bg="white", fg="blue").pack(anchor="w")
        self.combo_destino = ttk.Combobox(self.panel_lateral, values=self.estaciones, width=50, style="Custom.TCombobox")
        self.combo_destino.pack(pady=10)

        style.configure("Custom.TButton",
                background="#46d4ff",   
                foreground="blue",     
                borderwidth=2,
                padding=5)
        
        # Botones
        ttk.Button(self.panel_lateral, text="Calcular ruta", command=self.calcular_ruta, width=20, style="Custom.TButton").pack(pady=20)
        ttk.Button(self.panel_lateral, text="Borrar ruta",  command=lambda: self.borrar_ruta(True), width=20, style="Custom.TButton").pack(pady=10)
        
        # Panel lateral derecho
        self.ancho_panel_der = int(self.ancho_pantalla * 0.3)
        self.alto_panel_der = self.alto_pantalla - 100  
        self.overlay_panel = Image.new("RGBA", (self.ancho_panel_der, self.alto_panel_der), (255,255,255,0))
        self.dibujo_panel = ImageDraw.Draw(self.overlay_panel)
        self.tk_overlay_panel = ImageTk.PhotoImage(self.overlay_panel)
        self.id_overlay_panel = self.canvas.create_image(self.ancho_pantalla - self.ancho_panel_der - 50, 50, anchor="nw", image=self.tk_overlay_panel)

    def calcular_ruta(self):
        self.borrar_ruta(False)
        origen = self.combo_origen.get().strip()
        destino = self.combo_destino.get().strip()

        if not origen or not destino:
            messagebox.showerror("Error", "Selecciona origen y destino")
            return

        try:
            # Hora y día actual
            ahora = datetime.now()
            hora_actual = ahora.hour
            if (7 <= hora_actual < 9) or (18 <= hora_actual < 20):
                hora_dia = "rush"
            else:
                hora_dia = None

            dia_semana = ahora.weekday()
            if dia_semana < 5:
                dia = "weekday"
            elif dia_semana == 5:
                dia = "sat"
            else:
                dia = "sun"

            # Llamada al backend
            parametros = {"origin": origen, "destination": destino, "time_of_day": hora_dia, "day_of_week": dia}
            resp = requests.get(f"{URL_BACKEND}/path_q", params=parametros)
            resp.raise_for_status()
            datos_ruta = resp.json()
            ruta = datos_ruta["path"]

            # Panel derecho
            panel_width, panel_height = self.overlay_panel.size
            segmento_altura = (panel_height - 10) / max(len(ruta)-1, 1)
            x_panel = panel_width // 2

            # Dibujar líneas grises del overlay
            def dibujar_negroTrasparente(x1, y1, x2, y2):
                self.dibujo.line((x1 * self.escala, y1 * self.escala, x2 * self.escala, y2 * self.escala),
                                 fill=(34, 30, 31, 180), width=int(9 * self.escala))

            dibujar_negroTrasparente(133, 1, 133, 402)
            dibujar_negroTrasparente(90, 243, 261, 72)
            dibujar_negroTrasparente(135, 201, 462, 201)
            dibujar_negroTrasparente(135, 333, 454, 333)
            dibujar_negroTrasparente(351, 1, 351, 509)
            dibujar_negroTrasparente(260, 71, 358, 71)
            dibujar_negroTrasparente(452, 333, 467, 411)
            dibujar_negroTrasparente(465, 411, 509, 411)

            self.actualizar_overlay()

            for i in range(len(ruta) - 1):
                p1 = ruta[i]
                p2 = ruta[i + 1]

                s1 = p1["station"]
                s2 = p2["station"]

                x1 = self.coordenadas[s1]["x"] * self.escala
                y1 = self.coordenadas[s1]["y"] * self.escala
                x2 = self.coordenadas[s2]["x"] * self.escala
                y2 = self.coordenadas[s2]["y"] * self.escala

                # Pintar en la imagen
                color_linea = self.COLORES_LINEAS.get(p2["line"])
                color_transbordo = color_linea

                self.dibujar_segmento(x1, y1, x2, y2, color_linea)
                self.dibujar_circulo_estacion(x1, y1)
                self.dibujar_circulo_estacion(x2, y2)

                if i == 0:
                    y_actual = 10; 
                    self.dibujo_panel.text((x_panel - 165, y_actual-7), f"Hora de Salida: {ahora.strftime('%H:%M')}" , fill="black", font=ImageFont.truetype("arial.ttf", 15))
                    self.imagen_linea(self.IMAGENES_LINEAS.get(p2["line"]), x_panel, y_actual)
                else:
                    y_actual = i * segmento_altura
                    color_transbordo = self.COLORES_LINEAS.get(p1["line"])
                    if color_linea != color_transbordo:
                        color_transbordo = "#000000"
                        self.dibujo_panel.text((x_panel + 115, y_actual-7), "(Transbordo)", fill="black", font=ImageFont.truetype("arial.ttf", 15))
                        self.imagen_linea(self.IMAGENES_LINEAS.get(p2["line"]), x_panel, y_actual)

                # Dibujar en el panel derecho 
                y_sig = (i+1) * segmento_altura
                self.dibujo_panel.line((x_panel, y_actual, x_panel, y_sig), fill=color_linea, width=int(6*self.escala))
                self.dibujar_circulo_panel(x_panel, y_actual, color_transbordo)
                self.dibujar_circulo_panel(x_panel, y_sig, color_linea)
                self.dibujo_panel.text((x_panel + 18, y_actual-7), s1, fill="black", font=ImageFont.truetype("arial.ttf", 15))

                if i == (len(ruta) - 2):
                    self.dibujo_panel.text((x_panel + 18, y_sig-7), s2, fill="black", font=ImageFont.truetype("arial.ttf", 15))

                    coste_total = datos_ruta.get("total_cost")
                    tiempo_viaje = coste_total * 3
                    horas, minutos = divmod(tiempo_viaje, 60)
                    nueva_hora = ahora + timedelta(hours=horas, minutes=minutos)
                    
                    self.dibujo_panel.text((x_panel - 165, y_sig-7), f"Hora de Llegada: {nueva_hora.strftime('%H:%M')}" , fill="black", font=ImageFont.truetype("arial.ttf", 15))

            self.dibujo_panel.text((x_panel - 165, (panel_height / 2) - 10 ), f"( Paradas Totales: {len(ruta)-1} )", fill="black", font=ImageFont.truetype("arial.ttf", 15))

            self.actualizar_overlay()

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo obtener la ruta: {e}")

    def imagen_linea(self, imagen, x , y):
        imagen_linea = Image.open(imagen)
        ancho_original = imagen_linea.width
        alto_original = imagen_linea.height
        escala = (self.alto_pantalla * 0.05) / alto_original
        ancho_nuevo = int(ancho_original * escala)
        alto_nuevo = int(alto_original * escala)
        imagen_linea = imagen_linea.resize((ancho_nuevo, alto_nuevo), Image.LANCZOS)
        imagen_linea_actual = ImageTk.PhotoImage(imagen_linea)
        self.imgs_lineas_panel.append(imagen_linea_actual)
        self.canvas.create_image(self.ancho_pantalla - self.ancho_panel_der - 110 + x, 65 + y, anchor="nw", image=imagen_linea_actual)

    def dibujar_segmento(self, x1, y1, x2, y2, color):
        self.dibujo.line((x1, y1, x2, y2), fill=color, width=int(9 * self.escala))

    def dibujar_circulo_estacion(self, x, y):
        radio = int(8 * self.escala)
        self.dibujo.ellipse((x - radio, y - radio, x + radio, y + radio), fill="white", outline="black", width=int(4 * self.escala))
    
    def dibujar_circulo_panel(self, x, y, color):
        radio = int(8 * self.escala)
        self.dibujo_panel.ellipse((x - radio, y - radio, x + radio, y + radio), fill="white", outline=color, width=int(3 * self.escala))

    def actualizar_overlay(self):
        self.tk_overlay = ImageTk.PhotoImage(self.overlay)
        self.canvas.itemconfig(self.id_overlay, image=self.tk_overlay)

        self.tk_overlay_panel = ImageTk.PhotoImage(self.overlay_panel)
        self.canvas.itemconfig(self.id_overlay_panel, image=self.tk_overlay_panel)

    def borrar_ruta(self, limpiar_seleccion=False):
        # 1. Borrar todo
        self.canvas.delete("all")

        # 2. Redibujar imagen original
        self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.tk_imagen)

        # 3. Crear overlay nuevo
        ancho_nuevo = int(self.ancho_original * self.escala)
        alto_nuevo = int(self.alto_original * self.escala)
        self.overlay = Image.new("RGBA", (ancho_nuevo, alto_nuevo), (0, 0, 0, 0))
        self.dibujo = ImageDraw.Draw(self.overlay)
        self.tk_overlay = ImageTk.PhotoImage(self.overlay)
        self.id_overlay = self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.tk_overlay)

        self.overlay_panel = Image.new("RGBA", (self.ancho_panel_der, self.alto_panel_der), (255, 255, 255, 0))
        self.dibujo_panel = ImageDraw.Draw(self.overlay_panel)
        self.tk_overlay_panel = ImageTk.PhotoImage(self.overlay_panel)
        self.id_overlay_panel = self.canvas.create_image(
        self.ancho_pantalla - self.ancho_panel_der - 50, 50, anchor="nw", image=self.tk_overlay_panel)

        # 4. Limpiar combobox
        if limpiar_seleccion:
            self.combo_origen.set("")
            self.combo_destino.set("")

if __name__ == "__main__":
    raiz = tk.Tk()
    gui = MetroGUI(raiz)
    raiz.mainloop()
