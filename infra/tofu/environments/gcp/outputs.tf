output "api_endpoint" { value = module.llmproxy_app.api_endpoint }
output "database_endpoint" { value = module.postgres.database_endpoint }
output "redis_endpoint" { value = module.redis.redis_endpoint }
output "artifact_storage_name" { value = module.storage.artifact_storage_name }
output "secret_backend_name" { value = module.secrets.secret_backend_name }
output "kubernetes_namespace" { value = module.kubernetes_cluster.kubernetes_namespace }
