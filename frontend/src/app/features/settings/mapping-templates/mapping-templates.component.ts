import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MappingApiService, MappingTemplateOut } from '../../../core/mapping-api.service';

@Component({
  selector: 'app-mapping-templates',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './mapping-templates.component.html',
  styleUrl: './mapping-templates.component.css'
})
export class MappingTemplatesComponent implements OnInit {
  private api = inject(MappingApiService);

  loading = signal(true);
  templates = signal<MappingTemplateOut[]>([]);
  errorMessage = signal('');
  expandedId = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set('');
    try {
      this.templates.set(await this.api.listTemplates());
    } catch {
      this.errorMessage.set('Could not load mapping templates.');
    } finally {
      this.loading.set(false);
    }
  }

  toggle(id: string): void {
    this.expandedId.set(this.expandedId() === id ? null : id);
  }

  async remove(template: MappingTemplateOut): Promise<void> {
    if (!confirm(`Forget this mapping for ${template.category_name}? The next matching upload will need to be re-mapped.`)) {
      return;
    }
    try {
      await this.api.deleteTemplate(template.id);
      await this.refresh();
    } catch {
      this.errorMessage.set('Could not delete this template.');
    }
  }

  mappingEntries(template: MappingTemplateOut): { header: string; target: string }[] {
    return Object.entries(template.column_mapping).map(([header, target]) => ({ header, target }));
  }
}
