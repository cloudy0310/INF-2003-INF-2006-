output "alb_dns"            { value = aws_lb.app.dns_name }
output "app_url"            { value = "https://${local.app_fqdn}" }
output "admin_url"          { value = "https://${local.admin_fqdn}" }

output "rds_endpoint"       { value = aws_db_instance.postgres.address }
output "rds_port"           { value = aws_db_instance.postgres.port }
output "ddb_prices_table_arn" { value = aws_dynamodb_table.prices.arn }

output "cognito_user_pool_id" { value = aws_cognito_user_pool.pool.id }
output "cognito_domain"       { value = aws_ssm_parameter.cog_domain.value }
output "user_client_id"       { value = aws_ssm_parameter.cog_user_id.value }
output "admin_client_id"      { value = aws_ssm_parameter.cog_admin_id.value }

# secrets shown as sensitive; view via `terraform output -json` if needed
output "user_client_secret"  { value = aws_cognito_user_pool_client.user.client_secret  sensitive = true }
output "admin_client_secret" { value = aws_cognito_user_pool_client.admin.client_secret sensitive = true }
