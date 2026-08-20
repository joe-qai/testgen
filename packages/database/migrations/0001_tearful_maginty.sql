ALTER TABLE "workflow_runs" ALTER COLUMN "workflow_definition_id" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "workflow_runs" ALTER COLUMN "workflow_version_id" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "workflow_runs" ADD COLUMN "workflow_code" varchar(100);