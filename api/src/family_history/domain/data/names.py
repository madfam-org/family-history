"""Given names and surnames for synthetic families.

Common Mexican names, grouped by the era they were most given in, so a synthetic great-
grandmother is a Petra or a Macaria and a synthetic great-granddaughter a Regina or a Romina.
No entry identifies a real person: these are lexicon entries, combined at random.
"""

from __future__ import annotations

__all__ = [
    "FEMALE_CLASSIC",
    "FEMALE_COMPOUND",
    "FEMALE_CONTEMPORARY",
    "FEMALE_MODERN",
    "MALE_CLASSIC",
    "MALE_COMPOUND",
    "MALE_CONTEMPORARY",
    "MALE_MODERN",
    "PARTICLE_SURNAMES",
    "SURNAMES",
]

# Born before about 1945.
MALE_CLASSIC: tuple[str, ...] = (
    "José", "Juan", "Francisco", "Antonio", "Jesús", "Manuel", "Pedro", "Miguel", "Ramón",
    "Rafael", "Pablo", "Ignacio", "Salvador", "Gregorio", "Lorenzo", "Refugio", "Agustín",
    "Andrés", "Felipe", "Hilario", "Isidro", "Jacinto", "Lucio", "Marcelino", "Nicolás",
    "Porfirio", "Silverio", "Teodoro", "Valentín", "Benito", "Cirilo", "Crescencio", "Eusebio",
    "Faustino", "Tomás", "Anastasio", "Severiano", "Margarito",
)  # fmt: skip

FEMALE_CLASSIC: tuple[str, ...] = (
    "María", "Guadalupe", "Juana", "Josefa", "Dolores", "Rosario", "Refugio", "Concepción",
    "Teresa", "Isabel", "Consuelo", "Antonia", "Mercedes", "Socorro", "Francisca", "Manuela",
    "Petra", "Paula", "Ignacia", "Soledad", "Amparo", "Catalina", "Eulalia", "Felícitas",
    "Herminia", "Jovita", "Macaria", "Natividad", "Otilia", "Remedios", "Trinidad", "Zenaida",
    "Pilar", "Margarita",
)  # fmt: skip

# Born about 1945 to 1995.
MALE_CONTEMPORARY: tuple[str, ...] = (
    "Alberto", "Roberto", "Humberto", "Guillermo", "Eduardo", "Enrique", "Fernando", "Rodolfo",
    "Adolfo", "Carlos", "Jorge", "Javier", "Ricardo", "Sergio", "Arturo", "Alejandro", "Luis",
    "Raúl", "Óscar", "Héctor", "Armando", "Gerardo", "Mario", "Víctor", "Rafael", "Francisco",
    "Antonio", "Manuel", "Salvador", "Ignacio",
)  # fmt: skip

FEMALE_CONTEMPORARY: tuple[str, ...] = (
    "Alicia", "Leticia", "Patricia", "Gabriela", "Verónica", "Adriana", "Claudia", "Mónica",
    "Elena", "Ana", "Rosa", "Luisa", "Carmen", "Esperanza", "Silvia", "Laura", "Martha",
    "Norma", "Yolanda", "Lourdes", "Beatriz", "Irma", "Teresa", "Mercedes", "Guadalupe",
    "Margarita", "Consuelo", "Rosario",
)  # fmt: skip

# Born after about 1995.
MALE_MODERN: tuple[str, ...] = (
    "Santiago", "Mateo", "Sebastián", "Leonardo", "Emiliano", "Diego", "Daniel", "David",
    "Gael", "Iker", "Ángel", "Gabriel", "Alejandro", "Tadeo", "Rodrigo", "Maximiliano",
    "Emilio", "Joaquín", "Bruno", "Damián",
)  # fmt: skip

FEMALE_MODERN: tuple[str, ...] = (
    "Sofía", "Valentina", "Regina", "Ximena", "Camila", "Renata", "Fernanda", "Natalia",
    "Daniela", "Andrea", "Mariana", "Lucía", "Victoria", "Romina", "Isabella", "Valeria",
    "Paula", "Emilia", "Aitana", "Julieta",
)  # fmt: skip

MALE_COMPOUND: tuple[str, ...] = (
    "José María", "José Luis", "Juan Carlos", "José Antonio", "Juan José", "Luis Fernando",
    "José de Jesús", "Miguel Ángel",
)  # fmt: skip

FEMALE_COMPOUND: tuple[str, ...] = (
    "María de Jesús", "María Guadalupe", "María del Carmen", "María de los Ángeles",
    "Ana María", "María Elena", "María Luisa", "María del Refugio", "María Concepción",
)  # fmt: skip

SURNAMES: tuple[str, ...] = (
    "García", "Hernández", "Martínez", "López", "González", "Pérez", "Rodríguez", "Sánchez",
    "Ramírez", "Cruz", "Flores", "Gómez", "Morales", "Vázquez", "Reyes", "Jiménez", "Torres",
    "Díaz", "Gutiérrez", "Ruiz", "Mendoza", "Aguilar", "Ortiz", "Moreno", "Castillo",
    "Romero", "Álvarez", "Méndez", "Chávez", "Rivera", "Juárez", "Ramos", "Domínguez",
    "Herrera", "Medina", "Castro", "Vargas", "Guzmán", "Velázquez", "Muñoz", "Rojas",
    "Contreras", "Salazar", "Luna", "Ortega", "Santiago", "Guerrero", "Estrada", "Bautista",
    "Cortés", "Soto", "Alvarado", "Espinoza", "Lara", "Ávila", "Ríos", "Cervantes", "Silva",
    "Delgado", "Vega", "Márquez", "Sandoval", "Fernández", "León", "Carrillo", "Mejía",
    "Solís", "Núñez", "Rosas", "Valdez", "Ibarra", "Campos", "Santos", "Camacho", "Navarro",
    "Peña", "Maldonado", "Rosales", "Acosta", "Miranda", "Trejo", "Valencia", "Nava",
    "Pacheco", "Robles", "Molina", "Rangel", "Huerta", "Cárdenas", "Fuentes", "Ponce",
    "Zamora", "Ochoa", "Padilla", "Treviño",
)  # fmt: skip

#: Surnames that take a particle, as `(particle, surname)`.
PARTICLE_SURNAMES: tuple[tuple[str, str], ...] = (
    ("de la", "Garza"),
    ("de la", "Rosa"),
    ("de la", "Cruz"),
    ("de los", "Santos"),
    ("del", "Valle"),
    ("de", "León"),
)
