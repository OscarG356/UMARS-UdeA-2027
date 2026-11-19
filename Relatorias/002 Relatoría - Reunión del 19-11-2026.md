## 1. Novedades Generales
* **Nuevos integrantes:**
  * **Sara Galván** (Ing. de Sistemas) se incorpora al equipo para apoyar a Carlos en el área de **Comunicaciones**.
  * **Juan Pérez** (Ing. Mecánica) se incorpora al equipo para apoyar a Oscar en el área de **Estructura**.
* **Inscripción:** **Daniel Usme** presentó una propuesta de *abstract* para el documento de inscripción del proyecto.

---

## 2. Avances y Discusiones por Área

### Estructura
* **Eficiencia:** Juan propone utilizar únicamente **4 motores** en lugar de tracción en todas las ruedas, dejando las ruedas centrales solo como pivote con el objetivo de mejorar la eficiencia energética del rover.

### Sensores
* **Selección de componentes:** Walter comentó que estuvo evaluando distintas opciones de sensores en conjunto con Lu.

### Comunicaciones
* **Protocolo y manejo de errores:** Carlos presentó una propuesta de protocolo de comunicación con la estación en tierra que contempla cifrado con llave pública (RSA), envío de paquetes enumerados y control de *timeouts* para gestionar pérdidas de conexión:

```mermaid
sequenceDiagram
    title Transmission Flow
    participant T as Transmitter
    participant R as Receiver

    T->>R: request
    Note right of R: Communication request, transmitter starts<br/>a timer and re-sends in case of timeout.

    R->>T: public key
    Note right of R: RSA public key, receiver starts a timer and<br/>ends communication in case of timeout.

    rect rgba(0, 102, 204, 0.08)
        Note right of R: Enumerated packages
        T->>R: encrypted message[0]
        T->>R: encrypted message[1]
        Note over T,R: ...
        T->>R: encrypted message[n]
    end

    T->>R: end
    R->>T: ack
    Note right of R: Correct transmission confirmation
```

* **Disponibilidad de hardware (Antena):** No fue posible conseguir la antena a través de I+D; el tiempo estimado de espera es de **6 semanas**.
  * *Alternativa temporal:* Walter propuso utilizar los módulos **LoRa de Diana** mientras llega la antena definitiva para no detener el desarrollo.
* **Formato de datos en tierra:** Ante la consulta de Walter sobre la estructura de datos requerida para la estación en tierra, Carlos confirmó que puede enviarse en **texto plano**, ya que él se encargará de procesarlo y ordenarlo según sea necesario.

---

## 3. Estructura Actual del Equipo

```mermaid
---
config:
  flowchart:
    curve: step
---
flowchart TD
    %% Nodo Principal
    UMARS["<b>UMARS</b>"]

    %% Nivel 1: Líderes de Área
    UMARS --- WalterD["<b>Walter</b><br/>Dashboard"]
    UMARS --- Angee["<b>Angee</b><br/>Control"]
    UMARS --- Oscar["<b>Oscar</b><br/>Estructura"]
    UMARS --- Carlos["<b>Carlos</b><br/>Comunicaciones"]
    UMARS --- Lu["<b>Lu</b><br/>Sensores"]
    UMARS --- Daniel["<b>Daniel</b><br/>Visión"]

    %% Nivel 2: Integrantes
    Oscar --- WalterSub["Walter"]
    Oscar --- Juan["Juan Carlos"]
    Oscar --- Kevin["Kevin"]
    Carlos --- Sara["Sara"]

    %% Estilos para diferenciar jerarquías
    classDef proyecto fill:#1e293b,stroke:#0f172a,color:#ffffff,rx:8,ry:8
    classDef lider fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a,rx:6,ry:6
    classDef miembro fill:#f8fafc,stroke:#94a3b8,color:#334155,rx:6,ry:6

    class UMARS proyecto
    class WalterD,Angee,Oscar,Carlos,Lu,Daniel lider
    class WalterSub,Juan,Sara,Kevin miembro
```