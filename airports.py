import requests
import pandas as pd
import folium
from geopy.distance import geodesic
import webbrowser
import os
import heapq
import random

# Configura tu clave de API
API_KEY = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiI0IiwianRpIjoiNmFlMjRjNjA4NjEyNzI2Y2JlMTI2MTQxZDBmNmFjZWE1NWMwNWQzYjlmY2RjMzFlNzlkMTE5NjAzMzhiYmU4MDQ3YjY3OGUxYjQyODFmOGQiLCJpYXQiOjE3MzA4OTUyNzEsIm5iZiI6MTczMDg5NTI3MSwiZXhwIjoxNzYyNDMxMjcxLCJzdWIiOiIyMzUxNyIsInNjb3BlcyI6W119.hgw5qzV9lbptqQHv-osxwUBYh_5_Eve0psBddZA3K2nonQ5qZw84BjydyHVIMZ1FvsDAyizIDl7bamNOYYS54g'

# Cargar datos de aeropuertos y rutas
url_airports = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
columns_airports = ["Airport ID", "Name", "City", "Country", "IATA", "ICAO", "Latitude", "Longitude", "Altitude", 
                    "Timezone", "DST", "Tz database time zone", "Type", "Source"]
airports_df = pd.read_csv(url_airports, header=None, names=columns_airports)
airports_dict = airports_df.set_index('IATA').T.to_dict()

url_routes = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
columns_routes = ["Airline", "Airline ID", "Source Airport", "Source Airport ID", "Destination Airport", 
                  "Destination Airport ID", "Codeshare", "Stops", "Equipment"]
routes_df = pd.read_csv(url_routes, header=None, names=columns_routes)

# Función para obtener `skyId` y `entityId` de un aeropuerto
def obtener_datos_aeropuerto(iata_code):
    url = f"https://www.goflightlabs.com/retrieveAirport?access_key={API_KEY}&query={iata_code}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        for item in data:
            if item['skyId'] == iata_code:
                return item['skyId'], item['entityId']
    print(f"No se encontraron datos específicos para el código IATA {iata_code}")
    return None, None

# Función para obtener el precio del vuelo y detalles de la ruta más corta (usada para la ruta original)
def obtener_precio_vuelo(origin_sky_id, origin_entity_id, destination_sky_id, destination_entity_id, fecha):
    url = f"https://www.goflightlabs.com/retrieveFlights"
    params = {
        'access_key': API_KEY,
        'originSkyId': origin_sky_id,
        'destinationSkyId': destination_sky_id,
        'originEntityId': origin_entity_id,
        'destinationEntityId': destination_entity_id,
        'date': fecha
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if 'itineraries' in data and data['itineraries']:
            itinerary = data['itineraries'][0]
            price = itinerary['price']['formatted']
            departure = itinerary['legs'][0]['departure']
            arrival = itinerary['legs'][0]['arrival']
            airline = itinerary['legs'][0]['carriers']['marketing'][0]['name']
            return price, departure, arrival, airline
    print("No se encontraron precios o itinerarios válidos para esta consulta.")
    return None

# Función para obtener el itinerario de menor costo (ruta de menor costo)
def obtener_itinerario_menor_costo(origin_sky_id, origin_entity_id, destination_sky_id, destination_entity_id, fecha):
    url = f"https://www.goflightlabs.com/retrieveFlights"
    params = {
        'access_key': API_KEY,
        'originSkyId': origin_sky_id,
        'destinationSkyId': destination_sky_id,
        'originEntityId': origin_entity_id,
        'destinationEntityId': destination_entity_id,
        'date': fecha
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if 'itineraries' in data and data['itineraries']:
            itinerario_menor_costo = min(data['itineraries'], key=lambda x: float(x['price']['raw']))
            return itinerario_menor_costo
    print("No se encontraron itinerarios con información de precio válida.")
    return None

def obtener_coordenadas(iata_code):
    aeropuerto = airports_dict.get(iata_code)
    if aeropuerto:
        return float(aeropuerto["Latitude"]), float(aeropuerto["Longitude"])
    return None, None

def obtener_ruta_con_escalas(origen_code, destino_code):
    grafo = crear_grafo()
    distancia, ruta_iatas = dijkstra(grafo, origen_code, destino_code)
    
    aeropuertos_original = []
    for iata in ruta_iatas:
        aeropuerto = airports_dict.get(iata)
        if aeropuerto:
            aeropuertos_original.append({
                'name': aeropuerto['Name'],
                'IATA': iata,
                'latitude': float(aeropuerto['Latitude']),
                'longitude': float(aeropuerto['Longitude']),
            })
    return aeropuertos_original

def obtener_info_tramo_vuelo(origen_iata, destino_iata, fecha):
    """
    Utiliza la API de FlightLabs para obtener información detallada de cada tramo de vuelo.
    """
    origen_sky_id, origen_entity_id = obtener_datos_aeropuerto(origen_iata)
    destino_sky_id, destino_entity_id = obtener_datos_aeropuerto(destino_iata)
    
    if origen_sky_id and origen_entity_id and destino_sky_id and destino_entity_id:
        vuelo_info = obtener_precio_vuelo(origen_sky_id, origen_entity_id, destino_sky_id, destino_entity_id, fecha)
        if vuelo_info:
            price, departure, arrival, airline = vuelo_info
            return {
                "airline": airline,
                "price": price,
                "departure": departure,
                "arrival": arrival
            }
    return None

# Crear un grafo con los aeropuertos y distancias
def crear_grafo():
    grafo = {}
    for _, row in routes_df.iterrows():
        source_iata = row['Source Airport']
        dest_iata = row['Destination Airport']
        source_airport = airports_dict.get(source_iata)
        dest_airport = airports_dict.get(dest_iata)
        if source_airport and dest_airport:
            source_coords = (float(source_airport['Latitude']), float(source_airport['Longitude']))
            dest_coords = (float(dest_airport['Latitude']), float(dest_airport['Longitude']))
            distancia = geodesic(source_coords, dest_coords).kilometers
            if source_iata not in grafo:
                grafo[source_iata] = []
            grafo[source_iata].append((distancia, dest_iata))
    return grafo

# Algoritmo de Dijkstra para encontrar la ruta de distancia mínima
def dijkstra(grafo, origen_iata, destino_iata):
    cola_prioridad = [(0, origen_iata, [])]
    visitados = set()
    while cola_prioridad:
        (distancia_acumulada, nodo_actual, ruta_actual) = heapq.heappop(cola_prioridad)
        if nodo_actual == destino_iata:
            return distancia_acumulada, ruta_actual + [nodo_actual]
        if nodo_actual in visitados:
            continue
        visitados.add(nodo_actual)
        for distancia_vecino, vecino in grafo.get(nodo_actual, []):
            if vecino not in visitados:
                heapq.heappush(cola_prioridad, (distancia_acumulada + distancia_vecino, vecino, ruta_actual + [nodo_actual]))
    return None, []  

def obtener_info_ruta_azul(aeropuertos_original, fecha):
    """
    Calcula la información general de la ruta azul, incluyendo precio total, aerolínea, salida, llegada y distancia total.
    """
    total_price = 0
    total_distance = 0  # Variable para acumular la distancia total
    airline_info = None
    departure_time = None
    arrival_time = None
    route_info = []
    
    for i in range(len(aeropuertos_original) - 1):
        origen_iata = aeropuertos_original[i]['IATA']
        destino_iata = aeropuertos_original[i + 1]['IATA']
        
        # Obtener información detallada del tramo usando la API
        tramo_info = obtener_info_tramo_vuelo(origen_iata, destino_iata, fecha)
        
        if tramo_info:
            # Calcular la distancia entre el tramo de origen y destino
            origen_coords = (aeropuertos_original[i]['latitude'], aeropuertos_original[i]['longitude'])
            destino_coords = (aeropuertos_original[i + 1]['latitude'], aeropuertos_original[i + 1]['longitude'])
            distancia_tramo = geodesic(origen_coords, destino_coords).kilometers
            total_distance += distancia_tramo  # Acumular la distancia

            # Añadir la distancia a la información del tramo
            tramo_info['distance'] = f"{distancia_tramo:.2f} km"

            if i == 0:  # Primera escala: tomar la hora de salida y aerolínea
                departure_time = tramo_info['departure']
                airline_info = tramo_info['airline']
            if i == len(aeropuertos_original) - 2:  # Última escala: tomar la hora de llegada
                arrival_time = tramo_info['arrival']
            
            # Sumar el precio acumulado
            total_price += float(tramo_info['price'].replace('$', '').replace(',', ''))
            
            # Agregar tramo al resumen de ruta
            route_info.append(tramo_info)

    # Formatear el precio acumulado y la distancia total
    formatted_price = f"${total_price:.2f}"
    formatted_distance = f"{total_distance:.2f} km"
    
    return formatted_price, departure_time, arrival_time, airline_info, route_info, formatted_distance

# Función para crear y visualizar el mapa con ambas rutas
def crear_mapa(aeropuertos_menor_costo, aeropuertos_original, vuelo_info_menor_costo, fecha):
    world_map = folium.Map(location=[20, 0], zoom_start=2)

    # Añadir todos los aeropuertos al mapa como nodos
    for iata, airport in airports_dict.items():
        folium.CircleMarker(
            location=[float(airport['Latitude']), float(airport['Longitude'])],
            radius=2,
            popup=f"{airport['Name']} ({iata})",
            color="gray",
            fill=True,
            fill_opacity=0.7
        ).add_to(world_map)

    # Añadir la ruta de menor costo
    for i in range(len(aeropuertos_menor_costo) - 1):
        start = aeropuertos_menor_costo[i]
        end = aeropuertos_menor_costo[i + 1]
        
        # Obtener coordenadas de 'start' y 'end', ya sea de la API o del archivo de aeropuertos
        start_lat, start_lon = start['latitude'], start['longitude']
        end_lat, end_lon = end['latitude'], end['longitude']

        if start_lat == 0 or start_lon == 0:
            start_lat, start_lon = obtener_coordenadas(start['IATA'])
            start['latitude'], start['longitude'] = start_lat, start_lon
        if end_lat == 0 or end_lon == 0:
            end_lat, end_lon = obtener_coordenadas(end['IATA'])
            end['latitude'], end['longitude'] = end_lat, end_lon

        # Verificar que las coordenadas sean válidas
        if start_lat and start_lon and end_lat and end_lon:
            folium.PolyLine(
                locations=[(start_lat, start_lon), (end_lat, end_lon)],
                color="green",
                weight=2.5,
                opacity=1
            ).add_to(world_map)

        info_text = (
        f"<b>Aeropuerto:</b> {start['name']} ({start['IATA']})<br>"
        f"<b>Aerolínea:</b> {start.get('airline', 'N/A')}<br>"
        f"<b>Salida:</b> {start.get('departure', 'N/A')}<br>"
        f"<b>Llegada:</b> {end.get('arrival', 'N/A')}<br>"
        f"<b>Costo acumulado:</b> {start.get('price', 'N/A')}"
        )
        
        # Marcar cada aeropuerto en la ruta con nombre y código IATA
        folium.Marker(
        location=(start_lat, start_lon),
        popup=folium.Popup(info_text, max_width=300),
        icon=folium.Icon(color="blue", icon="plane", prefix="fa")
    ).add_to(world_map)

    # Marcar el destino final de la ruta de menor costo
    end = aeropuertos_menor_costo[-1]
    folium.Marker(
        location=(end['latitude'], end['longitude']),
        popup=f"{end['name']} ({end['IATA']})",
        icon=folium.Icon(color="red", icon="flag", prefix="fa")
    ).add_to(world_map)

    # Añadir información del vuelo para la ruta de menor costo
    if vuelo_info_menor_costo:
        price, departure, arrival, airline = vuelo_info_menor_costo
        info_general = (
            f"<b>Menor costo:</b> {price}<br>"
            f"<b>Salida:</b> {departure}<br>"
            f"<b>Llegada:</b> {arrival}<br>"
        )
        folium.Marker(
            location=[(aeropuertos_menor_costo[0]['latitude'] + aeropuertos_menor_costo[-1]['latitude']) / 2 + 0.5,
                    (aeropuertos_menor_costo[0]['longitude'] + aeropuertos_menor_costo[-1]['longitude']) / 2 + 0.5],
            popup=folium.Popup(info_general, max_width=300),
            icon=folium.Icon(color="green", icon="info-sign")
        ).add_to(world_map)

    #Ruta Original
    for i in range(len(aeropuertos_original) - 1):
        start = aeropuertos_original[i]
        end = aeropuertos_original[i + 1]
        
        # Obtener información detallada de la API para cada tramo de la ruta azul
        info = obtener_info_tramo_vuelo(start['IATA'], end['IATA'], fecha)
        
        folium.PolyLine(
            locations=[(start['latitude'], start['longitude']), (end['latitude'], end['longitude'])],
            color="blue",
            weight=2.5,
            opacity=1
        ).add_to(world_map)
        
        info_text = (
            f"<b>Aeropuerto:</b> {start['name']} ({start['IATA']})<br>"
            f"<b>Aerolínea:</b> {info['airline'] if info else 'N/A'}<br>"
            f"<b>Precio:</b> {info['price'] if info else 'N/A'}<br>"
            f"<b>Salida:</b> {info['departure'] if info else 'N/A'}<br>"
            f"<b>Llegada:</b> {info['arrival'] if info else 'N/A'}"
        )
        
        # Marcar cada aeropuerto en la ruta original (azul) con información de la API
        folium.Marker(
            location=(start['latitude'], start['longitude']),
            popup=folium.Popup(info_text, max_width=300),
            icon=folium.Icon(color="blue", icon="plane", prefix="fa")
        ).add_to(world_map)

    # Marcar el destino final en la ruta en azul
    end = aeropuertos_original[-1]
    folium.Marker(
        location=(end['latitude'], end['longitude']),
        popup=f"{end['name']} ({end['IATA']})",
        icon=folium.Icon(color="red", icon="flag", prefix="fa")
    ).add_to(world_map)

    total_price_azul, departure_azul, arrival_azul, airline_azul, route_info_azul, total_distance_azul = obtener_info_ruta_azul(aeropuertos_original, fecha)
    if total_price_azul:
        info_general_azul = (
            f"<b>Costo total:</b> {total_price_azul}<br>"
            f"<b>Distancia total:</b> {total_distance_azul}<br>"
            f"<b>Salida:</b> {departure_azul}<br>"
            f"<b>Llegada:</b> {arrival_azul}<br>"        )
        folium.Marker(
            location=[(aeropuertos_original[0]['latitude'] + aeropuertos_original[-1]['latitude']) / 2 - 0.5,
                    (aeropuertos_original[0]['longitude'] + aeropuertos_original[-1]['longitude']) / 2 - 0.5],
            popup=folium.Popup(info_general_azul, max_width=300),
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(world_map)
    
    return world_map

# Función principal para generar el mapa y mostrar detalles del vuelo
def generar_mapa_aeropuertos(origen_code, destino_code, fecha):
    aeropuertos_menor_costo = []
    aeropuertos_original = obtener_ruta_con_escalas(origen_code, destino_code)

    origen_sky_id, origen_entity_id = obtener_datos_aeropuerto(origen_code)
    destino_sky_id, destino_entity_id = obtener_datos_aeropuerto(destino_code)

    if origen_sky_id and origen_entity_id and destino_sky_id and destino_entity_id:
        # Obtener el itinerario de menor costo
        itinerario_menor_costo = obtener_itinerario_menor_costo(origen_sky_id, origen_entity_id, destino_sky_id, destino_entity_id, fecha)
        if itinerario_menor_costo:
            for leg in itinerario_menor_costo['legs'][0]['segments']:
                aeropuertos_menor_costo.append({
                'name': leg['origin']['name'],
                'latitude': leg['origin'].get('latitude', 0),
                'longitude': leg['origin'].get('longitude', 0),
                'IATA': leg['origin']['displayCode'],
                'airline': leg['marketingCarrier']['name'],
                    'departure': leg['departure'],
                    'arrival': leg['arrival'],  # Esto es para la llegada al próximo aeropuerto
                    'price': itinerario_menor_costo['price']['formatted']
            })
                aeropuertos_menor_costo.append({
                'name': leg['destination']['name'],
                'latitude': leg['destination'].get('latitude', 0),
                'longitude': leg['destination'].get('longitude', 0),
                'IATA': leg['destination']['displayCode'],
                'airline': leg['marketingCarrier']['name'],
                    'departure': leg['departure'],
                    'arrival': leg['arrival'],  # Esto es para la llegada al próximo aeropuerto
                    'price': itinerario_menor_costo['price']['formatted']
            })

            vuelo_info_menor_costo = (
                itinerario_menor_costo['price']['formatted'],
                itinerario_menor_costo['legs'][0]['departure'],
                itinerario_menor_costo['legs'][-1]['arrival'],
                itinerario_menor_costo['legs'][0]['carriers']['marketing'][0]['name']
            )

        # Crear el mapa con ambas rutas
        world_map = crear_mapa(aeropuertos_menor_costo, aeropuertos_original, vuelo_info_menor_costo, fecha)

        map_file = "ruta_aeropuertos.html"
        world_map.save(map_file)
        webbrowser.open(f"file://{os.path.realpath(map_file)}")
    else:
        print("No se pudo obtener información completa de los aeropuertos.")

# Ejemplo de uso
generar_mapa_aeropuertos("LIM", "PEK", "2024-11-18")
