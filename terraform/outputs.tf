output "ec2_public_ip" {
  value = aws_instance.streamlit.public_ip
}

output "rds_endpoint" {
  value = aws_db_instance.schooldb.address
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}
