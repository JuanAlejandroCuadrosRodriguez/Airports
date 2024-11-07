import requests
import pandas as pd
import folium
from geopy.distance import geodesic
import webbrowser
import os
import heapq

# Configura tu clave de API
API_KEY = ''

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

# Función para crear y visualizar el mapa con ambas rutas
def crear_mapa(aeropuertos_menor_costo, aeropuertos_original, vuelo_info_menor_costo, vuelo_info_original):
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
        folium.PolyLine(
            locations=[(start['latitude'], start['longitude']), (end['latitude'], end['longitude'])],
            color="green",
            weight=2.5,
            opacity=1
        ).add_to(world_map)

    # Añadir la ruta original
    for i in range(len(aeropuertos_original) - 1):
        start = aeropuertos_original[i]
        end = aeropuertos_original[i + 1]
        folium.PolyLine(
            locations=[(start['latitude'], start['longitude']), (end['latitude'], end['longitude'])],
            color="blue",
            weight=2.5,
            opacity=1
        ).add_to(world_map)

    # Añadir información del vuelo para cada ruta
    if vuelo_info_menor_costo:
        price, departure, arrival, airline = vuelo_info_menor_costo
        folium.Marker(
            location=[(aeropuertos_menor_costo[0]['latitude'] + aeropuertos_menor_costo[-1]['latitude']) / 2,
                       (aeropuertos_menor_costo[0]['longitude'] + aeropuertos_menor_costo[-1]['longitude']) / 2],
            popup=f"Menor costo: {price}, Salida: {departure}, Llegada: {arrival}, Aerolínea: {airline}",
            icon=folium.Icon(color="orange", icon="info-sign")
        ).add_to(world_map)

    if vuelo_info_original:
        price, departure, arrival, airline = vuelo_info_original
        folium.Marker(
            location=[(aeropuertos_original[0]['latitude'] + aeropuertos_original[-1]['latitude']) / 2,
                       (aeropuertos_original[0]['longitude'] + aeropuertos_original[-1]['longitude']) / 2],
            popup=f"Ruta original: {price}, Salida: {departure}, Llegada: {arrival}, Aerolínea: {airline}",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(world_map)

    return world_map

# Función principal para generar el mapa y mostrar detalles del vuelo
def generar_mapa_aeropuertos(origen_code, destino_code, fecha):
    aeropuertos_menor_costo = []
    aeropuertos_original = []

    origen_sky_id, origen_entity_id = obtener_datos_aeropuerto(origen_code)
    destino_sky_id, destino_entity_id = obtener_datos_aeropuerto(destino_code)

    if origen_sky_id and origen_entity_id and destino_sky_id and destino_entity_id:
        # Obtener el itinerario de menor costo
        itinerario_menor_costo = obtener_itinerario_menor_costo(origen_sky_id, origen_entity_id, destino_sky_id, destino_entity_id, fecha)
        if itinerario_menor_costo:
            for leg in itinerario_menor_costo['legs']:
                aeropuertos_menor_costo.append({
                'name': leg['origin']['name'],
                'latitude': leg['origin'].get('latitude', 0),  # Usamos get para evitar el error
                'longitude': leg['origin'].get('longitude', 0),  # Valor predeterminado si no existe el campo
                'IATA': leg['origin']['displayCode']
            })
                aeropuertos_menor_costo.append({
                'name': leg['destination']['name'],
                'latitude': leg['destination'].get('latitude', 0),
                'longitude': leg['destination'].get('longitude', 0),
                'IATA': leg['destination']['displayCode']
            })

            vuelo_info_menor_costo = (
                itinerario_menor_costo['price']['formatted'],
                itinerario_menor_costo['legs'][0]['departure'],
                itinerario_menor_costo['legs'][-1]['arrival'],
                itinerario_menor_costo['legs'][0]['carriers']['marketing'][0]['name']
            )

        # Obtener ruta original
        vuelo_info_original = obtener_precio_vuelo(origen_sky_id, origen_entity_id, destino_sky_id, destino_entity_id, fecha)
        if vuelo_info_original:
            aeropuertos_original.append({
                'name': airports_dict[origen_code]['Name'],
                'latitude': float(airports_dict[origen_code]['Latitude']),
                'longitude': float(airports_dict[origen_code]['Longitude']),
                'IATA': origen_code
            })
            aeropuertos_original.append({
                'name': airports_dict[destino_code]['Name'],
                'latitude': float(airports_dict[destino_code]['Latitude']),
                'longitude': float(airports_dict[destino_code]['Longitude']),
                'IATA': destino_code
            })

        # Crear el mapa con ambas rutas
        world_map = crear_mapa(aeropuertos_menor_costo, aeropuertos_original, vuelo_info_menor_costo, vuelo_info_original)

        map_file = "ruta_aeropuertos.html"
        world_map.save(map_file)
        webbrowser.open(f"file://{os.path.realpath(map_file)}")
    else:
        print("No se pudo obtener información completa de los aeropuertos.")

# Ejemplo de uso
generar_mapa_aeropuertos("LIM", "PEK", "2024-11-18")
