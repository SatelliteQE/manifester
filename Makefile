vault-login:
	@scripts/vault_login.py --login

vault-logout:
	@scripts/vault_login.py --logout

vault-status:
	@scripts/vault_login.py --status
