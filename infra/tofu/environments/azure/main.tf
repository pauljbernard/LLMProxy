module "network" { source = "../../modules/network" environment_name = "azure" project_name = "llmproxy" region = "eastus" vpc_cidr = "10.30.0.0/16" }
module "secrets" { source = "../../modules/secrets" environment_name = "azure" project_name = "llmproxy" }
module "storage" { source = "../../modules/storage" artifact_bucket_name = "llmproxy-azure-artifacts" }
module "postgres" { source = "../../modules/postgres" environment_name = "azure" project_name = "llmproxy" db_instance_class = "Standard_D2s_v3" }
module "redis" { source = "../../modules/redis" environment_name = "azure" project_name = "llmproxy" redis_instance_class = "C1" }
module "kubernetes_cluster" { source = "../../modules/kubernetes_cluster" environment_name = "azure" project_name = "llmproxy" region = "eastus" }
module "observability" { source = "../../modules/observability" environment_name = "azure" project_name = "llmproxy" }
module "llmproxy_app" {
  source = "../../modules/llmproxy_app"
  project_name = "llmproxy"
  environment_name = "azure"
  container_image = "llmproxy"
  container_image_tag = "latest"
  replica_count_api = 2
  replica_count_worker = 2
  enable_local_model_runtime = false
}
