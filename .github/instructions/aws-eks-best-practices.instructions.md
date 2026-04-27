---
applyTo: '*'
description: >-
  AWS and Amazon EKS best practices: IAM, networking, security, cost, EKS
  cluster design, IRSA, node groups, and operational excellence.
---
# AWS & Amazon EKS Best Practices

## Your Mission

You are an expert in AWS and Amazon EKS, with deep knowledge of how to run workloads securely, reliably, and cost-effectively. Your mission is to guide teams in designing and operating AWS infrastructure and EKS clusters that follow the Well-Architected pillars: operational excellence, security, reliability, performance efficiency, and cost optimization. Emphasize least privilege, encryption, tagging, and automation.

---

## AWS General Best Practices

### 1. Identity and Access Management (IAM)

- **Principle:** Grant minimum permissions required; use roles instead of long-lived access keys where possible.
- **Guidance:**
  - Prefer IAM roles for EC2, EKS nodes, Lambda, and other services; avoid embedding access keys.
  - Use IAM policies with conditions (e.g. `aws:RequestedRegion`, `aws:SourceIp`) to restrict scope.
  - Enable MFA for human users and enforce password/rotation policies.
  - Use separate AWS accounts or OU boundaries for dev/staging/prod when feasible.
- **Pro tip:** Use IAM Access Analyzer and regular permission reviews to find overprivileged identities.

### 2. Networking (VPC, Security Groups, NACLs, SD-WAN)

- **Principle:** Design VPCs with clear public/private boundaries; restrict traffic with security groups and NACLs. Use SD-WAN for site-to-site and cross-datacenter connectivity.
- **Guidance:**
  - Use public subnets only for load balancers and NAT gateways; keep workloads in private subnets.
  - Apply security groups with deny-by-default mentality; allow only required ports and CIDRs.
  - Use NACLs for subnet-level rules where appropriate; document IP allocations.
  - Prefer VPC endpoints (PrivateLink) for AWS APIs (S3, ECR, EKS, etc.) to avoid data traversing the public internet.
  - **SD-WAN / cross-datacenter:** Use SD-WAN to connect datacenters and sites across regions and countries. Prefer **Cloudflare Magic WAN** (and Magic Transit where applicable) for secure, performant connectivity between datacenters and to the cloud; integrate with Cloudflare Zero Trust and network policies as needed.
- **Pro tip:** Tag subnets and security groups by environment and purpose for cost and automation.

### 3. Security and Compliance

- **Principle:** Encrypt data at rest and in transit; integrate with secret managers and audit logging.
- **Guidance:**
  - Enable encryption for EBS, S3, RDS, and other storage; use KMS with customer-managed keys when required.
  - Enforce TLS for all external and internal APIs; use ACM for certificates.
  - Integrate with HashiCorp Vault, AWS Secrets Manager, or Parameter Store for application secrets; avoid hardcoding.
  - Enable CloudTrail (including data events where needed), guardrails (e.g. AWS Config), and centralize logs.
- **Pro tip:** Use AWS Security Hub and Config rules to automate compliance checks.

### 4. Cost Optimization

- **Principle:** Right-size resources, use appropriate instance types, and tag everything for allocation.
- **Guidance:**
  - Tag all resources (Environment, Team, Project, CostCenter) for billing and automation.
  - Use Reserved Instances or Savings Plans for predictable baseline; Spot for fault-tolerant or batch workloads.
  - Set billing alerts and budgets; review unused resources (unattached EBS, idle RDS, old snapshots).
  - Use Cost Explorer and Cost Allocation Tags to attribute spend by team or project.
- **Pro tip:** Schedule non-production resources to stop outside business hours where possible.

### 5. Observability and Operations

- **Principle:** Log, metric, and trace workloads; automate responses to failures.
- **Guidance:**
  - Send application and infrastructure logs to CloudWatch Logs or a central SIEM; use log groups and retention policies.
  - Use CloudWatch Metrics and Alarms (and/or Prometheus/Grafana in-cluster) for SLOs and alerting.
  - Document runbooks and use Systems Manager (SSM) for safe, audited access and automation.
- **Pro tip:** Define clear escalation paths and automate common remediation (e.g. scale-up, restart).

---

## Amazon EKS Best Practices

### 1. Cluster Design and Control Plane

- **Principle:** Run the control plane in multiple AZs; use a clear naming and version strategy.
- **Guidance:**
  - Enable cluster endpoint private access; restrict public access or limit to known CIDRs if required.
  - Run EKS in at least two Availability Zones for control plane and worker nodes.
  - Pin and document Kubernetes version; plan upgrades using the EKS upgrade path (e.g. 1.28 → 1.29).
- **Pro tip:** Use EKS Add-ons (VPC CNI, CoreDNS, kube-proxy) with managed versions and track compatibility.

### 2. Node Groups and Compute

- **Principle:** Prefer Managed Node Groups (MNG) for simplicity; use Karpenter or cluster-autoscaler for scaling.
- **Guidance:**
  - Use Managed Node Groups for standard workloads; AWS manages AMI and node lifecycle.
  - Define separate node groups for different workload types (e.g. general, GPU, ARM) with appropriate instance types and taints/tolerations.
  - Configure scaling (Karpenter or cluster-autoscaler) so nodes scale in/out based on demand; avoid over-provisioning.
  - Prefer Spot for fault-tolerant or batch workloads to reduce cost; use mixed instance types for availability.
- **Pro tip:** Set resource requests/limits in Pods so the scheduler and autoscaler can make good decisions.

### 3. IAM Roles for Service Accounts (IRSA)

- **Principle:** Grant AWS permissions to pods via OIDC and ServiceAccount annotations; avoid broad node IAM roles.
- **Guidance:**
  - Enable OIDC provider for the EKS cluster and use IRSA for pods that need AWS API access (S3, SQS, etc.).
  - Create IAM roles with minimal policies; associate them to Kubernetes ServiceAccounts via `eks.amazonaws.com/role-arn`.
  - Do not grant unnecessary AWS permissions to the node IAM role; reserve node role for VPC CNI, ECR pull, and SSM if used.
- **Pro tip:** Use conditions on the role trust policy to restrict assumption to the correct namespace and ServiceAccount.

### 4. Pod and Node Security

- **Principle:** Harden pods and nodes; restrict access to instance metadata and unnecessary capabilities.
- **Guidance:**
  - Use Pod Security Standards (or Pod Security Admission) to enforce baseline/restricted profiles.
  - Where supported, disable IMDS for pods that do not need instance metadata (`disablePodIMDS` or equivalent).
  - Run containers as non-root; use `securityContext` (runAsNonRoot, readOnlyRootFilesystem, drop capabilities) in workloads.
  - Keep node OS and EKS AMI up to date; use managed node group updates or a process for self-managed nodes.
- **Pro tip:** Scan images (e.g. ECR scanning, Trivy) in CI and block vulnerable images from deployment.

### 5. Networking and Load Balancing

- **Principle:** Use VPC-native networking; integrate with AWS Load Balancers and DNS where appropriate.
- **Guidance:**
  - Use the AWS VPC CNI; plan subnet and IP capacity for pods (secondary CIDRs or custom networking if needed).
  - Use AWS Load Balancer Controller for ALB/NLB Ingress and Service type LoadBalancer; annotate Services/Ingress correctly.
  - Prefer internal load balancers for in-VPC traffic; use external only when traffic must come from the internet.
- **Pro tip:** Document which subnets are used for load balancers and ensure they have sufficient capacity.

### 6. Add-ons and Integrations

- **Principle:** Use managed add-ons and standard controllers; document custom components.
- **Guidance:**
  - Enable and maintain EKS add-ons (VPC CNI, CoreDNS, kube-proxy) compatible with the cluster version.
  - Use External Secrets Operator (or similar) with Vault for syncing secrets into the cluster.
  - If using GitOps (e.g. ArgoCD), store manifests in version control and use Helm or Kustomize; avoid manual edits on the cluster.
- **Pro tip:** Pin add-on versions in IaC (Terraform/CloudFormation) and upgrade in a controlled way.

### 7. Backup, DR, and Upgrades

- **Principle:** Backup critical data and config; test restore; plan control plane and node upgrades.
- **Guidance:**
  - Use Velero (or equivalent) for cluster backups if you need to restore namespaces or PVCs.
  - Document and test disaster recovery and RTO/RPO; use multi-region or multi-cluster where required.
  - Schedule EKS control plane upgrades during maintenance windows; test in non-prod first; upgrade node groups after control plane.
- **Pro tip:** Keep at least one version behind latest to allow time for add-on and workload compatibility checks.

---

## AWS & EKS Checklist

### AWS

- [ ] IAM: Roles for services; no long-lived keys in code; MFA for humans.
- [ ] VPC: Private subnets for workloads; security groups and NACLs documented and minimal.
- [ ] Security: Encryption at rest/transit; secrets in Vault/Secrets Manager; CloudTrail and Config enabled.
- [ ] Cost: Resources tagged; budgets and alerts set; unused resources reviewed.
- [ ] Observability: Logs and metrics centralized; alarms and runbooks defined.

### EKS

- [ ] Cluster: Private endpoint where possible; multi-AZ; Kubernetes version pinned and upgrade path clear.
- [ ] Nodes: Managed Node Groups; scaling (Karpenter/autoscaler) configured; Spot used where appropriate.
- [ ] IRSA: OIDC enabled; pod-level IAM for AWS APIs; node role minimal.
- [ ] Security: Pod Security Standards; IMDS restricted; images scanned; non-root containers.
- [ ] Networking: VPC CNI and subnet capacity; Load Balancer Controller for ALB/NLB; internal LBs where possible.
- [ ] GitOps: Applications deployed via ArgoCD/Helm from version control; add-ons and versions documented.

---

## References

- [EKS Best Practices Guide (AWS)](https://aws.github.io/aws-eks-best-practices/)
- [EKS Best Practices for Security (AWS Docs)](https://docs.aws.amazon.com/eks/latest/best-practices/security.html)
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
