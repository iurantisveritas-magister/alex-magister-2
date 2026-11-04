# A-LEX MAGISTER 2 — puesta en la nube (sin instalar nada en tu computadora)

1. GitHub: crea un repositorio NUEVO y PRIVADO (nombre sugerido: alex-magister-2). No toques el repositorio original.
   Botón "uploading an existing file" y arrastra TODO el contenido de esta carpeta (descomprimida). Commit.
2. Render: New + > Blueprint > elige ese repositorio > Apply.
   Te pedirá valores:
   - ADMIN_EMAIL: tu correo (será tu usuario).
   - ADMIN_PASSWORD: una contraseña de 10 o más caracteres (la escribes tú, solo ahí).
   - ALEX_PROVEEDOR: anthropic u openai (puedes dejarlo vacío al inicio: funciona el expediente de ejemplo).
   - ALEX_MODELO: el nombre exacto de un modelo disponible en tu cuenta.
   - ALEX_ANTHROPIC_KEY o ALEX_OPENAI_KEY: la clave del proveedor elegido (solo ahí, nunca en un chat).
3. Cuando Render diga "Live", abre la dirección https://....onrender.com, entra con tu correo y contraseña.
Notas: el disco persistente requiere plan de pago en Render; verifica el precio vigente. Para cambiar el modelo o la clave,
edita las variables en Render (el consentimiento de cada expediente se invalida y se vuelve a pedir).
