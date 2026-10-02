"""Places, occupations and other vocabulary for synthetic families.

States are real (Mexican states and the US states where braceros and migrants went). Every
locality, parish and office is invented, and the names say so: each one carries a word such
as Ficción, Ejemplo, Ensayo, Supuesto or Imaginaria, so no reader can mistake it for a real
town.
"""

from __future__ import annotations

__all__ = [
    "BORDER_CROSSINGS",
    "COUNTRIES",
    "BRACERO_CENTERS",
    "CAUSES_OF_DEATH",
    "FICTIONAL_LOCALITIES",
    "FICTIONAL_US_LOCALITIES",
    "MX_STATES",
    "OCCUPATIONS",
    "ORIGIN_STATES",
    "US_STATES",
]

MX_STATES: tuple[str, ...] = (
    "Aguascalientes", "Baja California", "Baja California Sur", "Campeche", "Chiapas",
    "Chihuahua", "Ciudad de México", "Coahuila", "Colima", "Durango", "Estado de México",
    "Guanajuato", "Guerrero", "Hidalgo", "Jalisco", "Michoacán", "Morelos", "Nayarit",
    "Nuevo León", "Oaxaca", "Puebla", "Querétaro", "Quintana Roo", "San Luis Potosí",
    "Sinaloa", "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatán",
    "Zacatecas",
)  # fmt: skip

#: States the synthetic families come from (historic sending states of the Bajío and west).
ORIGIN_STATES: tuple[str, ...] = (
    "Jalisco", "Michoacán", "Guanajuato", "Zacatecas", "San Luis Potosí", "Durango",
    "Oaxaca", "Puebla", "Aguascalientes", "Nayarit",
)  # fmt: skip

COUNTRIES: dict[str, str] = {"MX": "México", "US": "Estados Unidos"}

US_STATES: tuple[str, ...] = ("California", "Texas", "Illinois", "Arizona", "Colorado")

#: `(kind, name)` of invented Mexican localities. Kinds: rancho, hacienda, pueblo, villa.
FICTIONAL_LOCALITIES: tuple[tuple[str, str], ...] = (
    ("rancho", "Rancho La Ficción"),
    ("rancho", "Rancho El Sinnombre"),
    ("rancho", "Rancho Ojo de Ensayo"),
    ("rancho", "Rancho Las Muestras"),
    ("rancho", "Rancho El Borrador"),
    ("rancho", "Rancho La Maqueta"),
    ("rancho", "Rancho Mezquite Supuesto"),
    ("hacienda", "Hacienda Santa Inventada"),
    ("hacienda", "Hacienda Los Supuestos"),
    ("hacienda", "Hacienda San Simulado"),
    ("hacienda", "Hacienda La Quimera"),
    ("pueblo", "San Ejemplo de las Flores"),
    ("pueblo", "Santa Prueba del Río"),
    ("pueblo", "San Hipotético"),
    ("pueblo", "Congregación El Modelo"),
    ("villa", "Villa Imaginaria"),
    ("villa", "Villa Ensayo de Juárez"),
)

#: Invented localities north of the border.
FICTIONAL_US_LOCALITIES: tuple[str, ...] = (
    "Campo Ejemplo",
    "Valle Ficticio",
    "Puerto Supuesto",
    "Colonia Imaginaria",
)

#: Invented bracero contracting centres (the program ran 1942–1964).
BRACERO_CENTERS: tuple[str, ...] = (
    "Centro de contratación de Villa Imaginaria",
    "Centro de contratación de Estación Ensayo",
)

#: Invented border crossing points.
BORDER_CROSSINGS: tuple[str, ...] = (
    "Garita de Paso Ensayo",
    "Garita de Puente Supuesto",
)

OCCUPATIONS: tuple[str, ...] = (
    "campesino", "jornalero", "arriero", "comerciante", "costurera", "maestra rural",
    "maestro", "carpintero", "panadero", "mecánico", "enfermera", "ingeniera", "contador",
    "chofer", "albañil", "obrera textil", "partera", "herrero", "estudiante",
)  # fmt: skip

CAUSES_OF_DEATH: tuple[str, ...] = (
    "fiebre", "pulmonía", "complicaciones del parto", "vejez", "accidente", "tifo",
    "enfermedad del corazón", "diabetes",
)  # fmt: skip
