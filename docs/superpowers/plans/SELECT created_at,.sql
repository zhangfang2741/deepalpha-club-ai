SELECT created_at,
       id,
       email,
       hashed_password,
       username,
       preferred_model,
       phone
FROM public."user"
order by created_at;