module "network" { source = "../../modules/network" environment_name = "local" project_name = "llmproxy" region = "local" vpc_cidr = "10.0.0.0/16" }
module "secrets" { source = "../../modules/secrets" environment_name = "local" project_name = "llmproxy" }
module "storage" { source = "../../modules/storage" artifact_bucket_name = "llmproxy-local-artifacts" }
module "postgres" { source = "../../modules/postgres" environment_name = "local" project_name = "llmproxy" db_instance_class = "local" }
module "redis" { source = "../../modules/redis" environment_name = "local" project_name = "llmproxy" redis_instance_class = "local" }
module "kubernetes_cluster" { source = "../../modules/kubernetes_cluster" environment_name = "local" project_name = "llmproxy" region = "local" }
module "observability" { source = "../../modules/observability" environment_name = "local" project_name = "llmproxy" }
module "llmproxy_app" {
  source = "../../modules/llmproxy_app"
  project_name = "llmproxy"
  environment_name = "local"
  container_image = "llmproxy"
  container_image_tag = "dev"
  replica_count_api = 1
  replica_count_worker = 1
  enable_local_model_runtime = true
}
