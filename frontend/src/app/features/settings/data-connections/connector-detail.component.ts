import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CategoryIconComponent } from './category-icon.component';
import { CATEGORY_GROUPS, Connector, getConnector } from './connectors.data';

@Component({
  selector: 'app-connector-detail',
  standalone: true,
  imports: [RouterLink, CategoryIconComponent],
  templateUrl: './connector-detail.component.html',
  styleUrl: './connector-detail.component.css'
})
export class ConnectorDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  connector = signal<Connector | null>(null);

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    const found = getConnector(id);
    if (!found) {
      this.router.navigateByUrl('/admin/settings/data-connections');
      return;
    }
    this.connector.set(found);
  }

  categoryLabel(): string {
    const c = this.connector();
    if (!c) return '';
    return CATEGORY_GROUPS.find((g) => g.id === c.categoryGroup)?.label ?? '';
  }

  goNext(): void {
    const c = this.connector();
    if (!c) return;
    this.router.navigate(['/admin/settings/data-connections', c.id, 'coming-soon']);
  }
}
