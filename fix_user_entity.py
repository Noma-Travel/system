"""One-off: create the missing user-profile entity for lucastoscanop@gmail.com.

Root cause: user_id d256d01b7 (md5(sub)[:9] for lucastoscanop@gmail.com) has full
org memberships (portfolio "Staging" + 6 orgs) but no `user` entity document, so
GET /_auth/user returns 404 "Entity not found" and the frontend never renders the
org switcher. The app normally creates this doc on first login via
create_user_funnel; this triggers that same path once.

Run from noma_backend_local/system with the venv active and AWS env set:
    source venv/bin/activate
    AWS_PROFILE=lucasToscano AWS_DEFAULT_REGION=us-east-1 python fix_user_entity.py
"""
from renglo.common import load_config
from renglo.auth.auth_controller import AuthController

USER_ID = "d256d01b7"
EMAIL = "lucastoscanop@gmail.com"

ac = AuthController(config=load_config())

pre = ac.get_entity("user", user_id=USER_ID)
print("BEFORE: /_auth/user status =", pre.get("status"), "|", pre.get("message"))
if pre.get("status") == 200:
    print("User entity already exists — nothing to do.")
    raise SystemExit(0)

res = ac.update_entity(
    "user",
    user_id=USER_ID,
    name="Lucas",
    slot_a="",                 # family-name slot (matches the /user PUT route mapping)
    email=EMAIL,
    ip="",
    lan="en",
    payload={},
)
print("CREATE: success =", res.get("success"), "| status =", res.get("status"), "|", res.get("message"))

post = ac.get_entity("user", user_id=USER_ID)
doc = post.get("document", {}) or {}
print("AFTER : /_auth/user status =", post.get("status"),
      "| _id =", doc.get("_id"), "| email =", doc.get("email"), "| is_active =", doc.get("is_active"))
