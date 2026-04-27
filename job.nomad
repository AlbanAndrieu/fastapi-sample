# nomad job stop --namespace=* -purge fastapi-sample
# aws --endpoint-url https://s3.gra.perf.cloud.ovh.net --profile s3-dev s3 rm s3://juicefs-gra-sample-${NOMAD_VAR_env} --recursive --exclude "*juicefs_uuid"
# nomad job run -var env=uat -var team=uat job.nomad

variable "env" {
  type    = string
  default = "dev"

  validation {
    condition     = var.env == "dev" || var.env == "uat" || var.env == "prod"
    error_message = "The env value must be valid env uat or prod."
  }
}

variable "team" {
  type    = string
  default = "uat"

  validation {
    condition     = var.team == "ateam" || var.team == "bteam" || var.team == "uat" || var.team == "prod" || var.team == "dev"
    error_message = "The env value must be valid team ateam or bteam."
  }
}

variable "datacenters" {
  type        = list(string)
  description = "List of datacenters to deploy to."
  default     = ["gra"]
}

variable "tls_domain" {
  type = string
  default = "fastapi-sample.service.gra.dev.consul" # service.gra.dev.consul
}

variable "alt_names" {
  type = string
  default = ""
}

job "fastapi-sample" {
  datacenters = var.datacenters
  namespace   = "infrastructure"
  type        = "service"

  # Meta keys are also interpretable.
  meta {
    version  = "v0.0.1"
    region   = "gra"
    dc       = "gra1"
    scope    = "test"
    service  = "fastapi-sample-${var.env}"
    team     = "${var.team}"
    env      = "${var.env}"
    run_uuid = "${uuidv4()}" # Always Deploy a New Job Version
  }

  group "fastapi-sample" {
    count = 1

    scaling {
      min     = 1
      max     = 4
      enabled = true

      policy {
        evaluation_interval = "2s"
        cooldown            = "2s"

        // check "active_connections" {
        //   source = "prometheus"
        //   query  = "nomad_client_allocs_cpu_total_percent{task='loki-${var.team}'}"

        //   strategy "target-value" {
        //     target = 70
        //   }
        // }
      }
    } # scaling

    # Spread allocations over each rack based on desired percentage
    spread {
      attribute = "${attr.unique.hostname}"  # meta.rack
      target "gra1nomadworker$${var.env}4" {
        percent = 60
      }
      target "gra1nomadworker$${var.env}2" {
        percent = 40
      }
    }

    ephemeral_disk {
      # Used to store index, cache, WAL
      # Nomad will try to preserve the disk between job updates
       size   = 500
       sticky  = true
       migrate = true
    }

    # Canary disable, because service is too big 10 G minimum and cluster is not sized for it, so auto_promote set to false
    update {
      max_parallel      = 1
      min_healthy_time  = "5s"
      healthy_deadline  = "5m"
      progress_deadline = "0"
      canary            = 0
      auto_revert       = var.env == "prod" ? true : false
      auto_promote      = var.env == "prod" ? true : false
    }

    network {
      port "http" {
        to  = 8080
      }

      port "redis" {
        to = 6379
      }

      port "redis-exporter" {
        to = 9121
      }
    }

    restart {
      attempts = 3
      interval = "5m"
      delay    = "25s"
      mode     = var.env == "dev" ? "fail" : "delay"
    }

    task "fastapi-sample" {
      driver = "docker"

      config {
        image = "[[ .CONTAINER_IMAGE ]]"
        ports = ["http"]

        labels = [
          {
            # "com.datadoghq.tags.env" = "${var.env}"
            # "com.datadoghq.tags.service" = "fastapi-sample"
            # "com.datadoghq.tags.version" = "${var.env}-0.0.1"
            # https://docs.datadoghq.com/fr/containers/docker/integrations/?tab=dockeradv2
            "com.datadoghq.ad.check_names" = "[\"openmetrics\",\"http_check\",\"guvicorn\"]"
            "com.datadoghq.ad.init_configs" = "[{},{},{}]"
            # "com.datadoghq.ad.instances": "[{\"apache_status_url\": \"http://fastapi-sample.service.gra.${var.env}.consul/server-status?auto\"}]"
            "com.datadoghq.ad.instances": "[{\"openmetrics_endpoint\": \"http://fastapi-sample.service.gra.${var.env}.consul/metrics\"},[{\"name\":\"fastapi-sample-v1\",\"url\":\"http://%%host%%/v1/ping\",\"timeout\":1},{\"name\":\"fastapi-sample-v2\",\"url\":\"http://%%host%%/v2/ping\",\"timeout\":1}]]"
            "com.datadoghq.ad.logs"="[{\"source\":\"guvicorn\",\"service\":\"fastapi-sample\",\"sourcecategory\":\"http_web_access\"}]"
            #"com.datadoghq.ad.logs"="[{\"source\":\"alternatives\",\"type\": \"file\",\"service\":\"alternatives",\"path\": \"/var/log/alternatives.log\"}]"
          }
        ]

        # force_pull = true
        shm_size = 536870912 # 512MB
        auth_soft_fail = true
        # image_pull_timeout = "25m"

        memory_hard_limit = 4096  # at 2G we will have OOM and the container will be killed
      } # config

      kill_timeout = "30s"
      # See https://moonape1226.medium.com/achieve-zero-downtime-when-upgrading-nomad-cluster-9c97d25606ad
      shutdown_delay = "10s"

      env {
        FASTAPI_ENV = "development"
        FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER=true
        SENTRY_ENVIRONMENT = "development"
        SENTRY_RELEASE = "[[ .CI_COMMIT_TAG ]]"
        SENTRY_DSN = "" # Disabled
        DD_VERSION = "[[ .CI_COMMIT_TAG ]]"
        DD_GIT_COMMIT_SHA = "[[ .CI_COMMIT_SHA ]]"
        DD_GIT_REPOSITORY_URL = "git@gitlab.com:AlbanAndrieu/fastapi-sample.git"
        DD_TRACE_SAMPLING_RULES = "[{\"service\":\"fastapi-sample\",\"resource\":\"GET /metrics\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /health\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /v1/ping\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /v2/ping\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /ping\",\"sample_rate\":0.01},{\"service\":\"fastapi-sample\",\"resource\":\"GET /cpu_task\",\"sample_rate\":1},{\"service\":\"fastapi-sample\",\"resource\":\"POST /io_task\",\"sample_rate\":1}]"
        # DD_PROFILING_PYTORCH_ENABLED=true
        DD_PROFILING_ENABLED=true
        DD_DYNAMIC_INSTRUMENTATION_ENABLED=true
        DD_API_SECURITY_ENABLED=true
        DD_APPSEC_ENABLED=false
        DD_APM_TRACING_ENABLED=true
        DD_LOGS_INJECTION=true
        DD_OTLP_CONFIG_RECEIVER_PROTOCOLS_GRPC_ENDPOINT="0.0.0.0:4317"
        # DD_OTLP_CONFIG_RECEIVER_PROTOCOLS_HTTP_ENDPOINT="0.0.0.0:4318"
        DD_APPSEC_AUTOMATED_USER_EVENTS_TRACKING=extended
        DD_DBM_PROPAGATION_MODE="full"
        DD_PROFILING_TIMELINE_ENABLED=true
        REDIS_URL="redis://fastapi-sample-redis.service.gra.${var.env}.consul:6380/0"
        # ALLOWED_HOSTS="[\"${NOMAD_HOST_IP_server}\",\"fastapi-sample.service.gra.${var.env}.consul\"]"
        EXPOSE_ENV = "${var.env}"
        EXPOSE_HOST = "localhost"
        EXPOSE_PORT = "8080"
        TARGET_ONE_HOST = "fastapi-sample.service.gra.${var.env}.consul"
        TARGET_TWO_HOST = "fastapi-sample.service.gra.${var.env}.consul"
        METRICS_ENABLED=true
      }

      vault {
        role = "nomad-cluster"
      }

# below was working
/*
      template {
        data        = <<EOF
{{ with pkiCert "pki_int/issue/example-dot-com" "common_name=fastapi-sample.service.gra.${var.env}.consul" }}
{{ .Cert }}{{ .CA }}{{ .Key }}
{{ end }}
EOF
        destination = "local/test.pem"

        # destination   = "${NOMAD_SECRETS_DIR}/bundle.pem"
        change_mode   = "restart"
      }
*/

#  error calling writeToFile: function is disabled
/*
      template {
        data        = <<EOF
{{ with pkiCert "pki_int/issue/example-dot-com" "common_name=fastapi-sample.service.gra.${var.env}.consul" }}
{{ .Cert }}{{ .CA }}{{ .Key }}
{{ .Key | writeToFile "examples/my-app.key" "root" "root" "0400" }}
{{ .CA | writeToFile "examples/ca.crt" "root" "root" "0644" }}
{{ .Cert | writeToFile "examples/my-app.crt" "root" "root" "0644" "append" }}
{{ end }}
EOF
        destination = "local/test.pem"

        # destination   = "${NOMAD_SECRETS_DIR}/bundle.pem"
        change_mode   = "restart"
      }
*/

# https://support.hashicorp.com/hc/en-us/articles/15712419079315-Templates-Using-nomad-attributes-when-creating-PKI-certificates-with-Vault
# {{ with secret "pki/issuer/d4d8fe33-4446-ea83-ff48-47832a7e6784/issue/test-example-dot-com" "common_name=fastapi-sample.service.gra.${var.env}.consul" "ip_sans=127.0.0.1" "format=pem" }}
# write pki_int/issue/example-dot-com common_name=fastapi-sample.service.gra.dev.consul
# See https://github.com/hashicorp/nomad/issues/19380

/*
      template {
data = <<EOF
{{ with secret "pki_int/issue/example-dot-com" "common_name=fastapi-sample.service.gra.${var.env}.consul" }}
{{ .Data.certificate }}
{{ .Data.issuing_ca }}
{{ .Data.private_key }}{{ end }}
EOF
       # destination   = "${NOMAD_SECRETS_DIR}/bundle.pem"
       destination   = "local/bundle.pem"
       change_mode   = "restart"
     }
*/

/*
template {
data = <<EOH
{{- $VAR1 := (printf "ip_sans=%s" (env "attr.unique.network.ip-address")) -}}
{{- with secret "pki_int/issue/test-example-dot-com" "common_name=${var.tls_domain}" "alt_names=${var.alt_names}" $VAR1 -}}
{{- .Data.certificate -}}
{{- printf "\n" -}}
{{- .Data.issuing_ca -}}
{{ end }}

EOH
destination = "local/bundle.pem"
change_mode = "restart"
}
*/

# vault write pki_int/issue/example-dot-com common_name="fastapi-sample.service.gra.dev.consul" ttl="24h"
/*
template {
  error_on_missing_key = true

  data = <<EOH
  {{- $VAR1 := (printf "ip_sans=%s" (env "attr.unique.network.ip-address")) -}}
  {{- with pkiCert "pki_int/issue/example-dot-com" "common_name=${var.tls_domain}" "alt_names=${var.alt_names}" $VAR1 -}}
  {{- .Cert -}}
  {{- printf "\n" -}}
  {{- .CA -}}
  {{ end }}

  EOH
  destination = "local/bundle2.pem"
  change_mode = "restart"
}
*/

      template {
        change_mode = "noop"

        data        = <<EOF
UVICORN_LOG_LEVEL=debug
OTEL_RESOURCE_ATTRIBUTES=service.name=fastapi-sample
OTEL_SERVICE_NAME=fastapi-sample
OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent.service.gra.${var.env}.consul:4317
PYROSCOPE_ENDPOINT="http://pyroscope.service.gra.${var.env}.consul"
EOF
        destination = "${NOMAD_SECRETS_DIR}/.env.local"

        env         = true
      } # template

      template {
        change_mode = "noop"

        data = <<EOF
# {{ with secret "infrastructure/elasticsearch-vars" }}
# AuthHeader = {{ printf "%s:%s" .Data.data.ELASTICSEARCH_USER .Data.data.ELASTICSEARCH_PASSWORD | base64URLEncode }}
# {{ end }}
{{ with secret "datascience/test/fastapi-sample" }}
{{.Data.data.ENV}}
{{ end }}
EOF
        destination = "${NOMAD_SECRETS_DIR}/env.authheader"
        env = true
      }

      service {
        name = "fastapi-sample"
        port = "http"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample.entrypoints=https",
          "traefik.http.routers.fastapi-sample.rule=Host(`fastapi-sample.service.gra.${var.env}.consul`)",
          "traefik.http.routers.fastapi-sample.tls=true",
          "traefik.http.routers.fastapi-sample.tls.options=myTLS12@file",
          "traefik.http.middlewares.redirect-https.redirectScheme.scheme=https",
          "traefik.http.middlewares.redirect-https.redirectScheme.permanent=true",
          # my-traefik-real-ip@file redirect-https
          "traefik.http.routers.fastapi-sample.middlewares=my-plugindemo@file,test-ratelimit@consulcatalog,test-inflightreq@consulcatalog",
          # 403 "traefik.http.routers.fastapi-sample.middlewares=my-crowdsec-bouncer-traefik-plugin@file",
          # "traefik.http.routers.fastapi-sample.middlewares=my-plugindemo@file,my-traefik-real-ip@file,my-crowdsec-bouncer-traefik-plugin@file,my-traefik-jwt-plugin@file",
          # test-ratelimit@consulcatalog,test-inflightreq@consulcatalog
          "traefik.http.middlewares.crowdsec.plugin.bouncer.forwardedheaderstrustedips=10.30.10.254,145.239.211.190,82.66.4.247", # LAN
          "traefik.http.middlewares.crowdsec.plugin.bouncer.clientTrustedips=10.30.0.115/32,10.20.0.115/32,10.10.0.126/32",
          #
          "traefik.http.middlewares.test-ratelimit.ratelimit.average=100",
          # "traefik.http.middlewares.test-ratelimit.ratelimit.period=1s"
          "traefik.http.middlewares.test-ratelimit.ratelimit.burst=50",
          "traefik.http.middlewares.test-inflightreq.inflightreq.amount=10",
          "traefik.http.middlewares.test-inflightreq.inflightreq.sourcecriterion.ipstrategy.excludedips=127.0.0.1/32,192.168.1.7,10.30.0.115/32,10.20.0.115/32,10.10.0.126/32",
          "traefik.http.services.fastapi-sample.loadbalancer.server.scheme=http",
          "traefik.http.services.fastapi-sample.loadbalancer.healthCheck.path=/health",
          "traefik.http.services.fastapi-sample.loadbalancer.healthCheck.interval=10s",
          "traefik.http.services.fastapi-sample.loadbalancer.healthCheck.timeout=3s",
          "squad=[[ .SQUAD ]]",
        ]

        check {
          name     = "server-alive"
          port     = "http"
          type     = "http"
          path     = "/health" # v1/ping /docs /metrics
          # 30s because can be heavy to lead, better to put it at this interval
          interval = "30s"
          timeout  = "5s"

          # header {
          #   Authorization = ["Basic ${AuthHeader}"]
          # }
        }

      } # service fastapi-sample

      resources {
        cpu    = 300 # MHz
        memory = 2512 # MB
      }
    } # task fastapi-sample

  } # group fastapi-sample

 group "fastapi-sample-redis" {
    count = 1

    network {
      port "redis" {
        to = 6379
      }
    }

    constraint {
      operator = "distinct_hosts"
      value = "true"
    }

    constraint {
      attribute = "${attr.kernel.name}"
      value = "linux"
    }

    spread {
      # Spread allocations equally over all nodes
      attribute = "${node.unique.id}"
      weight = 50
    }

    restart {
      attempts = 3
      interval = "5m"
      delay    = "25s"
      mode     = var.env == "dev" ? "fail" : "delay"
    }

    task "fastapi-sample-redis" {
      driver = "docker"

      config {
        image = "redis:8.4.0"

        args = [
          "--appendonly", "yes",
          "--appendfilename", "appendonly.aof",
          "--appendfsync", "everysec", # Options: always, everysec, no
          "--maxmemory", var.env == "prod" ? "800mb" : "300mb",
          "--maxmemory-policy", "allkeys-lru", # volatile-lru is the default
          "--maxmemory-samples", "5",
          "--databases", "16",
          "--save", "900 1", "--save", "300 10", "--save", "60 10000",
          "--tcp-keepalive", "60",
          "--timeout", "3000",
        ]

        # args = [
        #   "--requirepass",
        #   "mystery",
        # ]

        memory_hard_limit = 2048  # at 2G we will have OOM and the container will be killed

        ulimit {
           memlock = "-1"
           nofile = "65536"
           nproc = "65536"
        }

        ports = ["redis"]

        labels = [
          {
            # Unified Service Tagging
            "com.datadoghq.tags.env" = "${var.env}"
            "com.datadoghq.tags.service" = "fastapi-sample-redis"
            "com.datadoghq.tags.version" = "${var.env}-0.0.1"

            # Redis Integration Check
            "com.datadoghq.ad.check_names" = "[\"redisdb\"]"
            "com.datadoghq.ad.init_configs" = "[{}]"
            "com.datadoghq.ad.instances" = "[{\"host\":\"%%host%%\",\"port\":6379,\"tags\":[\"env:${var.env}\",\"service:fastapi-sample-redis\",\"component:cache\"],\"keys\":[\"*\"],\"command_stats\":true,\"disable_connection_cache\":false}]"

            # Log Collection
            "com.datadoghq.ad.logs" = "[{\"source\":\"redis\",\"service\":\"fastapi-sample-redis\",\"tags\":[\"env:${var.env}\",\"component:cache\"]}]"

            # Additional tags for metrics
            "com.datadoghq.tags.component" = "cache"
            "com.datadoghq.tags.team" = "platform"
          }
        ]
      } # config

      env {
        AWS_REGION = "gra"
      }

      service {
        name = "fastapi-sample-redis"
        port = "redis"

        tags = [
          "traefik.enable=true",
          "traefik.tcp.routers.fastapi-sample-redis.service=fastapi-sample-redis",
          "traefik.tcp.routers.fastapi-sample-redis.entrypoints=tcp-redis-juicefs",
          "traefik.tcp.routers.fastapi-sample-redis.rule=HostSNI(`*`)",
          "traefik.tcp.routers.fastapi-sample-redis.tls=false"
        ]

        check {
          name     = "alive"
          type     = "tcp"
          interval = "10s"
          timeout  = "2s"
        }

      } # service fastapi-sample-redis

      resources {
        cpu    = 300 # MHz
        memory = 300 # Mb
      }

    } # task fastapi-sample-redis

  } # group fastapi-sample-redis

  group "fastapi-sample-redis-exporter" {
    count = 1

    network {
      port "redis-exporter" {
        to = 9121
      }
    }

    task "fastapi-sample-redis-exporter" {
      driver = "docker"

      config {
        # See https://github.com/oliver006/redis_exporter
        image = "oliver006/redis_exporter:v1.77.0"
        ports = ["redis-exporter"]

        args = [
          "-redis.addr=redis://fastapi-sample-redis.service.gra.${var.env}.consul:6380",
          "-log-format=json"
        ]

      }

      env {
        # REDIS_ADDR = "redis://fastapi-sample-redis.service.gra.${var.env}.consul:6380"
        REDIS_EXPORTER_INCL_SYSTEM_METRICS=true
      }

      service {
        name = "fastapi-sample-redis-exporter"
        port = "redis-exporter"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample-redis-exporter.entrypoints=http",
          "traefik.http.routers.fastapi-sample-redis-exporter.rule=Host(`fastapi-sample-redis-exporter.service.gra.${var.env}.consul`)",
        ]

        check {
          type = "http"
          path = "/metrics"
          timeout = "30s"
          interval = "15s"
        }
      } # service

      resources {
        cpu    = 100 # Mhz
        memory = 64  # MB
      }
    } # task fastapi-sample-redis-exporter
  } # group fastapi-sample-redis-exporter

  # group "smi" {
  #   task "smi" {
  #     driver = "docker"
  #
  #     config {
  #       image = "nvidia/cuda:12.8.1-base-ubuntu22.04"
  #       command = "nvidia-smi"
  #     }
  #
  #     resources {
  #       device "nvidia/gpu" {
  #         count = 1
  #
  #         # Add an affinity for a particular model
  #         affinity {
  #           attribute = "${device.model}"
  #           value     = "Tesla K80"
  #           weight    = 50
  #         }
  #       }
  #     }
  #   }
  # } # group smi

}
